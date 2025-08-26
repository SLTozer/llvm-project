// Purpose:
//      Check that \DexExpectWatchValue applies no penalties when expected
//      values are found.
//
// UNSUPPORTED: system-darwin
//
// RUN: %dexter_regression_test_cxx_build %s -o %t
// RUN: %dexter_regression_test_run --binary %t -- %s | FileCheck %s
// CHECK: expect_watch_value.cpp:

unsigned long Factorial(int n) {
    volatile unsigned long fac = 1; // DexLabel('entry')

    for (int i = 1; i <= n; ++i)
        fac *= i;                   // DexLabel('loop')

    return fac;                     // DexLabel('ret')
}

int main()
{
    return Factorial(8);
}

/*
---
!where {lines: 12}:
  !value n: 8
!where {lines: 15}:
  !value i: !unknown i
  !value fac: 
    - 1
    - 1
    - 2
    - 6
    - 24
    - 120
    - 720
    - 5040
  !value n: 8
!where {lines: 17}:
  !value fac: 40320
  !value n: 8
...
*/
