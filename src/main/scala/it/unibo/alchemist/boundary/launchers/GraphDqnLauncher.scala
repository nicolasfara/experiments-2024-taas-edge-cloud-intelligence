package it.unibo.alchemist.boundary.launchers

import com.google.common.collect.Lists
import it.unibo.alchemist.boundary.{Launcher, Loader, Variable}
import it.unibo.alchemist.core.Simulation
import it.unibo.alchemist.model.{DecayLayer, Layer, LearningLayer}
import it.unibo.alchemist.model.molecules.SimpleMolecule
import it.unibo.alchemist.utils.Molecules
import it.unibo.alchemist.utils.PythonModules.rlUtils
import learning.model.ExponentialDecay
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
class GraphDqnLauncher(
    val batch: java.util.ArrayList[String],
    val globalRounds: Int,
    val seedName: String,
    val globalBufferSize: Int,
    val actionSpaceSize: Int,
    val boundedVariables: java.util.List[String],
    val targetSwapPeriod: Int,
) extends Launcher {

  private val logger: Logger = LoggerFactory.getLogger(this.getClass.getName)
  private val errorQueue = new ConcurrentLinkedQueue[Throwable]()
  implicit private val executionContext: ExecutionContext = ExecutionContext.global
  // private var learners: Map[Long, py.Dynamic] = Map.empty

  override def launch(loader: Loader): Unit = {
    val instances = loader.getVariables
    val prod = cartesianProduct(instances, batch)
    val removeIncompatibleConfigurations = if (boundedVariables.asScala.toList.nonEmpty) {
      prod.filter(instance => isCompatible(instance, boundedVariables.asScala.toList))
    } else {
      prod
    }
    println(s"Number of compatible configurations: ${removeIncompatibleConfigurations.size}")
    removeIncompatibleConfigurations.zipWithIndex.foreach { case (instance, index) =>
      println("Configuration " + index)
      val decay = new ExponentialDecay(0.99, 0.2, 0.02)
      var learner: py.Dynamic = null
      var seedIsSet = false
      Range.inclusive(1, globalRounds).foreach { iter =>
        println(s"Starting Global Round: $iter")
        println(s"Epsilon Decay: ${decay.value()}")
        instance.addOne("globalRound" -> iter)
        println(s"${Thread.currentThread().getName}")

        val decayLayer = new DecayLayer(decay.value())
        val seed = instance(seedName).asInstanceOf[Double].toLong
        val newSeed = iter + Math.pow(10, (seed + 1)).toLong
        instance.addOne("randomAugmentedSeed", newSeed)
        if (!seedIsSet) {
          learner = rlUtils.DQNTrainer(actionSpaceSize, seed, targetSwapPeriod, globalBufferSize)
          seedIsSet = true
        }
        val sim = loader.getWith[Any, Nothing](instance.asJava)
        sim.getEnvironment.addLayer(new SimpleMolecule(Molecules.decay), decayLayer.asInstanceOf[Layer[Any, Nothing]])
        val learnerLayer = new LearningLayer(learner)
        sim.getEnvironment.addLayer(new SimpleMolecule(Molecules.learner), learnerLayer.asInstanceOf[Layer[Any, Nothing]])
        runSimulationSync(sim, index, instance)
        decay.update()
        learner.snapshot_model("networks", iter, seed)
      }
      val seed = instance(seedName).asInstanceOf[Double].toLong

      val alpha: Double = instance.getOrElse("alpha", 0.0).asInstanceOf[Double]
      val beta: Double = instance.getOrElse("beta", 0.0).asInstanceOf[Double]
      val gamma: Double = instance.getOrElse("gamma", 0.0).asInstanceOf[Double]
      learner.save_stats("data-learning", seed, alpha, beta, gamma)
    }
    /*
    val decay = new ExponentialDecay(0.99, 0.3, 0.02)
    Range.inclusive(1, globalRounds).foreach { iter =>
      println(s"Starting Global Round: $iter")
      println(s"Number of simulations: ${prod.size}")
      println(s"Epsilon Decay: ${decay.value()}")
      prod.zipWithIndex
        .foreach { case (instance, index) =>
          instance.addOne("globalRound" -> iter)
          val sim = loader.getWith[Any, Nothing](instance.asJava)
          println(s"${Thread.currentThread().getName}")
          val decayLayer = new DecayLayer(decay.value())
          sim.getEnvironment.addLayer(new SimpleMolecule(Molecules.decay), decayLayer.asInstanceOf[Layer[Any, Nothing]])
          val seed = instance(seedName).asInstanceOf[Double].toLong

          learners.get(seed) match {
            case Some(_) =>
            case _       => learners = learners + (seed -> rlUtils.DQNTrainer(actionSpaceSize, seed, 3000, globalBufferSize))
          }

          val learnerLayer = new LearningLayer(learners.getOrElse(seed, throw new IllegalStateException("Learner not found!")))
          sim.getEnvironment.addLayer(new SimpleMolecule(Molecules.learner), learnerLayer.asInstanceOf[Layer[Any, Nothing]])
          runSimulationSync(sim, index, instance)
        }
      decay.update()
    }*/
    // learners.foreach { case (seed, l) => l.save_stats("data", seed) }
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

  private def isCompatible(instance: mutable.Map[String, Serializable], variables: List[String]): Boolean = {
    val bounded = variables.filter(instance.contains).map(k => instance(k).asInstanceOf[Double]).sum
    isValid(bounded)
  }
  private def isValid(value: Double): Boolean =
    value > 0.99 && value < 1.01
}
