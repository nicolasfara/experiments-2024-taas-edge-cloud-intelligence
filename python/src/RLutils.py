import torch
from torch_geometric.data import HeteroData
import random
from torch_geometric.data import Data, Batch
import torch.nn.functional as F
from torch_geometric.nn import GATConv, to_hetero, SAGEConv
import torch.nn as nn
from torch.utils.tensorboard import SummaryWriter
import pandas as pd
import math
import numpy as np

def create_graph(
        app_features,
        infrastructural_features,
        edges_app_to_infrastructural,
        edges_app_to_app,
        edges_infrastructural_to_infrastructural,
        edges_features_app_to_infrastructural,
        edges_features_app_to_app,
        edges_features_infrastructural_to_infrastructural
):
    data = HeteroData()
    data["application"].x = app_features
    data["infrastructure"].x = infrastructural_features
    data ["application", "app_to_infrastructural", "infrastructure"].edge_index = edges_app_to_infrastructural
    data ["application", "app_to_app", "application"].edge_index = edges_app_to_app
    data ["infrastructure", "infrastructural_to_infrastructural", "infrastructure"].edge_index = edges_infrastructural_to_infrastructural
    data ["application", "app_to_infrastructural", "infrastructure"].edges_attr = edges_features_app_to_infrastructural
    data ["application", "app_to_app", "application"].edges_attr = edges_features_app_to_app
    data ["infrastructure", "infrastructural_to_infrastructural", "infrastructure"].edges_attr = edges_features_infrastructural_to_infrastructural
    return data

class GraphReplayBuffer:

    def __init__(self, capacity):
        self.capacity = capacity
        self.buffer = []
        self.position = 0
        self.random = random

    def set_seed(self, seed):
        self.random.seed(seed)

    def size(self):
        return len(self.buffer)

    def push(self, graph_observation, actions, rewards, next_graph_observation):
        if len(self.buffer) < self.capacity:
            self.buffer.append(None)
        self.buffer[self.position] = (graph_observation, actions, rewards, next_graph_observation)
        self.position = (self.position + 1) % self.capacity

    def sample(self, batch_size):
        sample = self.random.sample(self.buffer, batch_size)
        observations = [s[0] for s in sample]
        actions = [s[1] for s in sample]
        rewards = [s[2] for s in sample]
        next_graph_observations = [s[3] for s in sample]
        return (Batch.from_data_list(observations), torch.cat(actions), torch.cat(rewards), Batch.from_data_list(next_graph_observations))

    def __len__(self):
        return len(self.buffer)

class GCN(torch.nn.Module):
    def __init__(self, hidden_dim, output_dim):
        super(GCN, self).__init__()
        self.conv1 = GATConv((-1, -1), hidden_dim, add_self_loops=False, bias=True)
        # self.conv1 = SAGEConv((-1, -1), hidden_dim, bias=True)
        # self.conv2 = GATConv(hidden_dim, hidden_dim, add_self_loops=False, bias=True)
        # self.conv3 = GATConv(hidden_dim, hidden_dim, add_self_loops=False, bias=True)
        self.lin1 = torch.nn.Linear(hidden_dim, hidden_dim)
        self.lin2 = torch.nn.Linear(hidden_dim, output_dim)

    def forward(self, x, edge_index):
        x = self.conv1(x, edge_index)
        x = torch.tanh(x)
        # x = self.conv2(x, edge_index)
        # x = torch.relu(x)
        # x = self.conv3(x, edge_index)
        # x = torch.relu(x)
        x = self.lin1(x)
        x = torch.tanh(x)
        x = self.lin2(x)
        return x

class DQNTrainer:
    def __init__(self, output_size, seed, target_frequency):
        self.train_summary_writer = SummaryWriter()
        self.output_size = output_size
        self.replay_buffer = GraphReplayBuffer(400)
        self.random = random
        self.hidden_size = 8
        self.set_seed(seed)
        self.model = GCN(hidden_dim=self.hidden_size, output_dim=output_size)
        self.target_model = GCN(hidden_dim=self.hidden_size, output_dim=output_size)
        self.target_model.load_state_dict(self.model.state_dict())
        self.optimizer = torch.optim.Adam(self.model.parameters(), 0.001)
        self.ticks = 0
        self.executedToHetero = False
        self.stats = pd.DataFrame(columns=['tick', 'reward', 'values', 'next_values', 'target_values', 'loss'])
        self.target_frequency = target_frequency
        self.next_update_at = target_frequency

    def add_experience(self, graph_observation, actions, rewards, next_graph_observation):
        self.replay_buffer.push(graph_observation, actions, rewards, next_graph_observation)

    def save_stats(self, path, seed):
        self.stats.to_csv(f'{path}/stats-seed_{seed}.csv', index=False)

    def set_seed(self, seed):
        self.random.seed(seed)
        self.replay_buffer.set_seed(seed)
        np.random.seed(seed)
        torch.manual_seed(seed)
        torch.backends.cudnn.deterministic = True
        torch.cuda.manual_seed(seed)

    def biased_random(self):
        # if(self.random.random() < 0.9):
        #     return 0
        # else:
        return self.random.randint(0, self.output_size - 1)

    def select_action(self, graph_observation, epsilon):
        if self.random.random() < epsilon:
            return torch.tensor([self.biased_random() for _ in range(graph_observation['application'].x.shape[0])])
        else:
            self.model.eval()
            with torch.no_grad():
                return self.model(graph_observation.x_dict, graph_observation.edge_index_dict)['application'].max(dim=1)[1]

    def toHetero(self, data):
        if not self.executedToHetero:
            metadata = data.metadata()
            self.model = to_hetero(self.model, metadata, aggr='sum')
            self.target_model = to_hetero(self.target_model, metadata, aggr='sum')
            self.executedToHetero = True

    def train_step_dqn(self, batch_size, gamma=0.99, seed=42):
        if len(self.replay_buffer) < batch_size:
            return 0

        # epochs = min(math.ceil(self.replay_buffer.size() / 2), 50)
        epochs = 20
        self.train_summary_writer.add_scalar('buffer size', self.replay_buffer.size(), self.ticks)
        self.train_summary_writer.add_scalar('epochs', epochs, self.ticks)

        for _ in range(epochs):
            self.model.train()
            obs, actions, rewards, nextObs = self.replay_buffer.sample(batch_size)
            av_reward = torch.mean(rewards)
            self.train_summary_writer.add_scalar('average_rewards', av_reward, self.ticks)
            rewards = torch.nn.functional.normalize(rewards, dim=0)
            values = self.model(obs.x_dict, obs.edge_index_dict)['application'].gather(1, actions.unsqueeze(1))
            nextValues = self.target_model(nextObs.x_dict, nextObs.edge_index_dict)['application'].max(dim=1)[0].detach()
            targetValues = rewards + (gamma * nextValues)
            loss = nn.MSELoss()(values, targetValues.unsqueeze(1))
            self.optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1)
            self.optimizer.step()
            # self.log_gradients_in_model(self.model, self.ticks)
            av_values = torch.mean(values)
            av_next_values = torch.mean(nextValues)
            av_target_values = torch.mean(targetValues)
            self.train_summary_writer.add_scalar('average_values', av_values, self.ticks)
            self.train_summary_writer.add_scalar('average_next_values', av_next_values, self.ticks)
            self.train_summary_writer.add_scalar('average_target_values', av_target_values, self.ticks)
            self.train_summary_writer.add_scalar('loss', loss.item(), self.ticks)
            self.next_update_at -= 1
            self.stats = self.stats._append({
                'tick': self.ticks,
                'reward': av_reward.item(),
                'values': av_values.item(),
                'next_values': av_next_values.item(),
                'target_values': av_target_values.item(),
                'loss': loss.item()
            }, ignore_index=True)

            if self.next_update_at == 0:
                del self.target_model
                metadata = obs.metadata()
                self.target_model = GCN(hidden_dim=self.hidden_size, output_dim=self.output_size)
                self.target_model = to_hetero(self.target_model, metadata, aggr='sum')
                self.target_model.load_state_dict(self.model.state_dict())
            self.ticks += 1
            self.target_model.eval()
            self.next_update_at = self.target_frequency
        return loss.item()

    def log_gradients_in_model(self, model, step):
        for tag, value in model.named_parameters():
            if value.grad is not None:
                self.train_summary_writer.add_histogram(tag + "/grad", value.grad.cpu(), step)
    def model_snapshot(self, dir, iter):
        torch.save(self.model, f'{dir}/network-iteration-{iter}')

class BatteryRewardFunction:
    def compute_difference(self, observation, next_observation):
        battery_status_t1 = observation["application"].x[:, 0]
        battery_status_t2 = next_observation["application"].x[:, 0]
        rewards = battery_status_t2 - battery_status_t1
        return rewards

    def compute_threshold(self, observation, next_observation):
        battery_status = next_observation["application"].x[:, 0]
        rewards = torch.where(battery_status > 50, torch.tensor(0.), torch.tensor(-10.))
        return rewards


class CostRewardFunction:

    def compute(self, observation, next_observation):
        costs = next_observation["application"].x[:, 0]
        return 1 - (torch.exp(2 * costs))
        # return -costs
        # rewards = -10 * torch.log(100 * costs + 1)
        # return torch.where(rewards == 0, torch.tensor(50))
        return rewards
class MixedRewardFunction:

    def __init__(self):
        self.scale_factor = 50

    def compute(self, observation, next_observation, alpha):
        battery_status = 1 - (torch.exp(2 * next_observation["application"].x[:, 1]))
        costs = 1 - (torch.exp(2 * next_observation["application"].x[:, 0]))
        rewards = alpha * battery_status + (1 - alpha) * costs
        raise Exception(rewards)
        return rewards

# Just a quick test
# if __name__ == '__main__':
#
#     graph = create_graph(
#         app_features=torch.tensor([[100.0, 2.0], [100.0, 1.0], [3.0, 1.0]]),
#         infrastructural_features=torch.tensor([[1.0, 1.0, 1.0], [2.0, 2.0, 2.0], [3.0, 3.0, 3.0]]),
#         edges_app_to_infrastructural=torch.tensor([[0, 1, 0], [1, 2, 2]]),
#         edges_app_to_app=torch.tensor([[0], [1]]),
#         edges_infrastructural_to_infrastructural=torch.tensor([[1], [2]]),
#         edges_features_app_to_infrastructural=torch.tensor([[1.0, 1.0], [2.0, 2.0], [3.0, 3.0]]),
#         edges_features_app_to_app=torch.tensor([[1.0, 2.0]]),
#         edges_features_infrastructural_to_infrastructural=torch.tensor([[2.0, 1.0]])
#     )
#
#     print(graph['application'].x.shape[0])
#
#     graph2 = create_graph(
#         app_features=torch.tensor([[100.0, 2.0], [70.0, 1.0], [30.0, 1.0]]),
#         infrastructural_features=torch.tensor([[1.0, 1.0], [2.0, 2.0], [3.0, 3.0]]),
#         edges_app_to_infrastructural=torch.tensor([[0, 1, 0], [1, 2, 2]]),
#         edges_app_to_app=torch.tensor([[0], [1]]),
#         edges_infrastructural_to_infrastructural=torch.tensor([[1], [2]]),
#         edges_features_app_to_infrastructural=torch.tensor([[1.0, 1.0], [2.0, 2.0], [3.0, 3.0]]),
#         edges_features_app_to_app=torch.tensor([[1.0, 2.0]]),
#         edges_features_infrastructural_to_infrastructural=torch.tensor([[2.0, 1.0]])
#     )
#
#     print('---------------------------------- Checking GCN ----------------------------------')
#
#     # Checks that the GCN is correctly created
#     model = GCN(hidden_dim=32, output_dim=8)
#     model = to_hetero(model, graph.metadata(), aggr='sum')
#     output = model(graph.x_dict, graph.edge_index_dict)
#     print(output['application'])
#     print('OK!')
#
#     print('-------------------------------- Checking Learning -------------------------------')
#     # Checks learning step
#     trainer = DQNTrainer(8)
#     for i in range(10):
#         trainer.add_experience(graph, torch.tensor([1, 2, 3]), torch.tensor([1.0, 0.0, -10.0]), graph2)
#     trainer.toHetero(graph)
#     trainer.train_step_dqn(batch_size=5, gamma=0.99, update_target_every=10)
#     print(trainer.select_action(graph, 0.0))
#     print('OK!')
#
#     print('---------------------------- Checking RF Battery -----------------------------')
#     reward_function = BatteryRewardFunction()
#     diff = reward_function.compute_difference(graph, graph2)
#     th = reward_function.compute_threshold(graph, graph2)
#     print(diff)
#     print(th)
#
#     print('---------------------------- Checking RF Costs -----------------------------')
#     reward_function = CostRewardFunction()
#     reward = reward_function.compute(graph, graph2)
#     print(reward)