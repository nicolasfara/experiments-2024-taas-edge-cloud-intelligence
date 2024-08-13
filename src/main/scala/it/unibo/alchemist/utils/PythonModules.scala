package it.unibo.alchemist.utils

import me.shadaj.scalapy.py

object PythonModules {

  val torch: py.Module = py.module("torch")
  val rlUtils: py.Module = py.module("RLutils")

}
