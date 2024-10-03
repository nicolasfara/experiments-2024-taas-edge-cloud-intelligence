package it.unibo.alchemist.model.implementations.actions

import it.unibo.alchemist.model.actions.AbstractLocalAction
import it.unibo.alchemist.model.molecules.SimpleMolecule
import it.unibo.alchemist.model.{Action, AllocatorProperty, Environment, Node, Position, Reaction}

import scala.jdk.CollectionConverters.{CollectionHasAsScala, IteratorHasAsScala}

class ModularizationRuntime[T, P <: Position[P]](
    environment: Environment[T, P],
    node: Node[T],
) extends AbstractLocalAction[T](node) {
  private val infrastructuralMolecule = new SimpleMolecule("infrastructuralDevice")
  private lazy val allocator: AllocatorProperty[T, P] = node.getProperties.asScala
    .find(_.isInstanceOf[AllocatorProperty[T, P]])
    .map(_.asInstanceOf[AllocatorProperty[T, P]])
    .getOrElse(throw new IllegalStateException(s"`AllocatorProperty` not found for node ${node.getId}"))

  override def cloneAction(node: Node[T], reaction: Reaction[T]): Action[T] = ???

  override def execute(): Unit = {
    val surrogate = environment.getNodes
      .iterator()
      .asScala
      .find(_.contains(infrastructuralMolecule))
      .getOrElse(throw new IllegalStateException("No surrogate found"))
    allocator.setComponentsAllocation(
      Map("it.unibo.alchemist.Gradient" -> surrogate.getId),
    )
  }
}
