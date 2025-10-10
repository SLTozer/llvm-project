// Purpose:
//      Check that \DexExpectStepOrder applies no penalty when the expected
//      order is found.
//
// UNSUPPORTED: system-darwin
//
// RUN: %dexter_regression_test_cxx_build %s -o %t
// RUN: %dexter_regression_test_run --binary %t -- %s | FileCheck %s
// CHECK: correct_line_steps: 6

int main() // !dex_label main
{
  volatile int a = 1;
  volatile int b = 1;
  volatile int c = 1;

  volatile int x = 1;
  volatile int y = 1;
  volatile int z = 1;
  return 0;
}

/*
---
!where {function: main}:
  !steps order: [13, 14, 15, !label main+6, !label main+7, !label main+8]
...
*/

