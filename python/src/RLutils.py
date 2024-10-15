import torch
import random
from torch_geometric.data import HeteroData
import random
from torch_geometric.data import Data, Batch
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


graph = create_graph(
    app_features=torch.tensor([[1.0, 2.0], [2.0, 1.0], [3.0 , 1.0]]),
    infrastructural_features=torch.tensor([[1.0, 1.0], [2.0, 2.0], [3.0, 3.0]]),
    edges_app_to_infrastructural=torch.tensor([[0, 1, 0], [1, 2, 2]]),
    edges_app_to_app=torch.tensor([[0], [1]]),
    edges_infrastructural_to_infrastructural=torch.tensor([[1], [2]]),
    edges_features_app_to_infrastructural=torch.tensor([[1.0, 1.0], [2.0, 2.0], [3.0, 3.0]]),
    edges_features_app_to_app=torch.tensor([[1.0,2.0]]),
    edges_features_infrastructural_to_infrastructural=torch.tensor([[2.0, 1.0]])
)

graph2 = create_graph(
    app_features=torch.tensor([[1.0, 2.0], [2.0, 1.0], [3.0 , 1.0]]),
    infrastructural_features=torch.tensor([[1.0, 1.0], [2.0, 2.0], [3.0, 3.0]]),
    edges_app_to_infrastructural=torch.tensor([[0, 1, 0], [1, 2, 2]]),
    edges_app_to_app=torch.tensor([[0], [1]]),
    edges_infrastructural_to_infrastructural=torch.tensor([[1], [2]]),
    edges_features_app_to_infrastructural=torch.tensor([[1.0, 1.0], [2.0, 2.0], [3.0, 3.0]]),
    edges_features_app_to_app=torch.tensor([[1.0,2.0]]),
    edges_features_infrastructural_to_infrastructural=torch.tensor([[2.0, 1.0]])
)

class GraphReplayBuffer:

    def __init__(self, capacity):
        self.capacity = capacity
        self.buffer = []
        self.position = 0

    def push(self, graph_observation, actions, rewards, next_graph_observation):
        if len(self.buffer) < self.capacity:
            self.buffer.append(None)
        self.buffer[self.position] = (graph_observation, actions, rewards, next_graph_observation)
        self.position = (self.position + 1) % self.capacity

    def sample(self, batch_size):
        sample = random.sample(self.buffer, batch_size)
        observations = [s[0] for s in sample]
        actions = [s[1] for s in sample]
        rewards = [s[2] for s in sample]
        next_graph_observations = [s[3] for s in sample]
        return (Batch.from_data_list(observations), torch.cat(actions), torch.cat(rewards), Batch.from_data_list(next_graph_observations))

    def __len__(self):
        return len(self.buffer)

class DQNTrainer:
    def __init__(self, env):
        self.env = env
        self.n_input = self.env.observation_space['agent0'].shape[0] + 1
        self.n_output = env.action_space['agent0'].n
        self.model = ##GCN(input_dim=self.n_input, hidden_dim=32, output_dim=self.n_output)
        self.target_model = ##GCN(input_dim=self.n_input, hidden_dim=32, output_dim=self.n_output)
        self.target_model.load_state_dict(self.model.state_dict())
        self.optimizer = torch.optim.RMSprop(self.model.parameters(), lr=0.0001)
        self.replay_buffer = GraphReplayBuffer(6000)
        self.writer = ##tensorboard.SummaryWriter()
        self.episode_rewards = []
        self.episode_losses = []
        self.episode_obstacle_hits = []
        self.rewards_buffer = []
        self.obstacle_hits_buffer = []

    def train_step_dqn(self, batch_size, model, target_model, ticks, gamma=0.99, update_target_every=10):
        if len(self.replay_buffer) < batch_size:
            return 0
        model.train()
        self.optimizer.zero_grad()
        obs, actions, rewards, nextObs = self.replay_buffer.sample(batch_size)

        values = model(obs).gather(1, actions.unsqueeze(1))
        nextValues = target_model(nextObs).max(dim=1)[0].detach()
        targetValues = rewards + gamma * nextValues
        loss = nn.SmoothL1Loss()(values, targetValues.unsqueeze(1))
        self.optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_value_(model.parameters(), 1)
        self.optimizer.step()

        if ticks % update_target_every == 0:
            target_model.load_state_dict(model.state_dict())
        self.writer.add_scalar('Loss', loss.item(), ticks)
        return loss.item()


replay_buffer = GraphReplayBuffer(5)
replay_buffer.push(graph, torch.tensor([1, 2]), torch.tensor([1.0]), graph2)
replay_buffer.push(graph, torch.tensor([1, 2]), torch.tensor([1.0]), graph2)
