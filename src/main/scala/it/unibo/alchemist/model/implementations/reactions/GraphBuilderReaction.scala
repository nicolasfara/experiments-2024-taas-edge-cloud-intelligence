package it.unibo.alchemist.model.implementations.reactions

import it.unibo.alchemist.model.{Environment, Node, Position, TimeDistribution}

import scala.jdk.CollectionConverters.CollectionHasAsScala
import it.unibo.alchemist.model.molecules.SimpleMolecule
import it.unibo.alchemist.utils.PythonModules.{rlUtils, torch}
import it.unibo.alchemist.utils.Molecules

import scala.language.implicitConversions
import me.shadaj.scalapy.py.SeqConverters
import me.shadaj.scalapy.py

trait Tensor
case class Vector(data: List[Int]) extends Tensor
case class Matrix(data: List[(Int, List[Int])]) extends Tensor

class GraphBuilderReaction[T, P <: Position[P]](
  environment: Environment[T, P],
  distribution: TimeDistribution[T]
) extends AbstractGlobalReaction(environment, distribution) {

  private implicit def toMolecule(name: String): SimpleMolecule = new SimpleMolecule(name)

  override protected def executeBeforeUpdateDistribution(): Unit = {
    val infrastructuralNodes = nodes
      .filter(n => n.contains(Molecules.infrastructural))
      .map(n => n.getId)
    val applicationNodes = nodes
      .filterNot(n => n.contains(Molecules.infrastructural))
      .map(n => n.getId)
    val app2app = getEdgeIndexes(applicationNodes, applicationNodes)
    val infr2infr = getEdgeIndexes(infrastructuralNodes, infrastructuralNodes)
    val app2infr = getEdgeIndexes(applicationNodes, infrastructuralNodes)
  }

  private def filterNeighbors(neighbors: List[Int], nodes: List[Int]): List[Int] = {
    neighbors.filter(neigh => nodes.contains(neigh))
  }

  private def getEdgeIndexes(sourceNodes: List[Int], endNodes: List[Int]): Matrix = {
    val d = nodes
      .filter(n => sourceNodes.contains(n.getId))
      .map(n => (n.getId, getNeighbors(n)))
      .map { case (s, neighs) => (s, filterNeighbors(neighs, endNodes)) }
    Matrix(d)
  }

  private def toTorchTensor(data: Tensor): py.Dynamic = data match {
    case v: Vector => torch.Tensor(v.data, dtype = torch.Long)
    case m: Matrix => m.data
      .map { case (self, neighs) => List(List.fill(neighs.length)(self)) }
      .map { m => torch.Tensor(m, dtype = torch.Long) }
      .takeRight(m.data.length - 1)
      .foldLeft(torch.Tensor(m.data.head, dtype = torch.long))((elem, acc) => torch.cat(List(acc, elem), dim = 1))
  }

  private def getNeighbors(n: Node[T]): List[Int] = {
    environment
      .getNeighborhood(n)
      .getNeighbors
      .stream()
      .map(neigh => neigh.getId)
      .toList
      .asScala
      .toList
  }

}
