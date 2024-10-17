package it.unibo.alchemist.boundary.launchers

import com.google.common.collect.Lists
import it.unibo.alchemist.boundary.{Launcher, Loader, Variable}
import it.unibo.alchemist.core.Simulation
import it.unibo.alchemist.model.{Layer, LearningLayer}
import it.unibo.alchemist.model.molecules.SimpleMolecule
import it.unibo.alchemist.utils.PythonModules.rlUtils
import me.shadaj.scalapy.py
import org.slf4j.{Logger, LoggerFactory}

import java.util.concurrent.ConcurrentLinkedQueue
import scala.collection.mutable
import scala.concurrent.duration.Duration
import scala.concurrent.{Await, ExecutionContext, Future}
import scala.jdk.CollectionConverters.{IteratorHasAsScala, _}
import scala.util.{Failure, Success}

/** Simple launcher for DQN based on graph
  * @param batch
  * @param globalRounds
  * @param seedName
  * @param globalBufferSize
  */
abstract class GraphDqnLauncher(
    val batch: java.util.ArrayList[String],
    val globalRounds: Int,
    val seedName: String,
    val globalBufferSize: Int,
) extends Launcher {

  type ExperienceBuffer
  private val logger: Logger = LoggerFactory.getLogger(this.getClass.getName)
  private val errorQueue = new ConcurrentLinkedQueue[Throwable]()
  implicit private val executionContext: ExecutionContext = ExecutionContext.global
  override def launch(loader: Loader): Unit = {
    val modules = 2 // Number of modules
    val totalAction = modules * 2 // Number of actions
    val learner = rlUtils.DQNTrainer(totalAction)
    val instances = loader.getVariables
    val prod = cartesianProduct(instances, batch)
    initializeNetwork()

    Range.inclusive(1, globalRounds).foreach { iter =>
      logger.info(s"Starting Global Round: $iter")
      logger.info(s"Number of simulations: ${prod.size}")
      prod.zipWithIndex
        .to(LazyList)
        .map { case (instance, index) =>
          instance.addOne("globalRound" -> iter)
          val sim = loader.getWith[Any, Nothing](instance.asJava)
          val seed = instance(seedName).asInstanceOf[Double].toLong
          println(s"${Thread.currentThread().getName}")
          val learnerLayer = new LearningLayer(learner)
          sim.getEnvironment.addLayer(new SimpleMolecule("learner"), learnerLayer.asInstanceOf[Layer[Any, Nothing]])
          runSimulationSync(sim, index, instance)
        }
    }

    saveNetworks()
    println("[DEBUG] finished ")
  }

  private def cartesianProduct(
      variables: java.util.Map[String, Variable[_]],
      variablesNames: java.util.List[String],
  ): List[mutable.Map[String, Serializable]] = {
    val l = variablesNames
      .stream()
      .map { variable =>
        val values = variables.get(variable)
        values.stream().map(e => variable -> e).toList
      }
      .toList
    Lists
      .cartesianProduct(l)
      .stream()
      .map(e => mutable.Map.from(e.iterator().asScala.toList))
      .iterator()
      .asScala
      .toList
      .asInstanceOf[List[mutable.Map[String, Serializable]]]
  }

  private def runSimulationSync(
      simulation: Simulation[Any, Nothing],
      index: Int,
      instance: mutable.Map[String, Serializable],
  )(implicit executionContext: ExecutionContext): Simulation[Any, Nothing] = {

    val future = Future {
      simulation.play()
      simulation.run()
      simulation.getError.ifPresent(error => throw error)
      logger.info("Simulation with {} completed successfully", instance)
      simulation
    }
    future.onComplete {
      case Success(_) =>
        logger.info("Simulation {} of {} completed", index + 1, instance.size)
      case Failure(exception) =>
        logger.error(s"Failure for simulation with $instance", exception)
        errorQueue.add(exception)
    }
    Await.result(future, Duration.Inf)
  }

  protected def neuralNetworkInjection(simulation: Simulation[Any, Nothing], iteration: Int): Unit

  protected def initializeNetwork(): Unit

  protected def saveNetworks(): Unit

  protected def improvePolicy(simulationsExperience: Seq[ExperienceBuffer], iteration: Int): Unit

  protected def loadNetworks(iteration: Int): (py.Dynamic, py.Dynamic)

  protected def cleanAfterRound(simulations: List[Simulation[Any, Nothing]]): Unit

}