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
    volatile unsigned long fac = 1; // !dex_label entry

    for (int i = 1; i <= n; ++i)
        fac *= i;                   // !dex_label loop

    return fac;                     // !dex_label ret
}

int main()
{
    return Factorial(8);
}

/*
---
!where {lines: !label entry}:
  !value n: 8
!where {lines: !range [!label loop, !label loop]}:
  !value i: !unknown i
  !value fac: [1, 1, 2, 6, 24, 120, 720, 5040]
  !value n: 8
!where {lines: !label ret}:
  !value fac: 40320
  !value n: 8
...
*/
