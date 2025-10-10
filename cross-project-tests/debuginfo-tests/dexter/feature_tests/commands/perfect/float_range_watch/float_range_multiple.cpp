// Purpose:
//      Check that \DexExpectWatchValue float_range=0.5 considers a range
//      difference of 0.49999 to be an expected watch value for multple values.
//
// UNSUPPORTED: system-darwin
//
// RUN: %dexter_regression_test_cxx_build %s -o %t
// RUN: %dexter_regression_test_run --binary %t -- %s | FileCheck %s
// CHECK: correct_steps: 6

int main() {
  float a = 1.0f;
  float b = 100.f;
  a = a + 0.4999f;
  a = a + b; // !dex_label check1
  return a;  // !dex_label check2
}

// DexExpectWatchValue('a', '1.0', '101.0', from_line=ref('check1'), to_line=ref('check2'), float_range=0.5)
/*
---
!where {lines: !range [!label check1, !label check2]}:
  !value a: !float {range: 0.5, values: [1.0, 101.0]}
...
*/