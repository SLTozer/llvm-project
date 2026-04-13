// Tests that nested !where blocks are properly constrained by their parent !where blocks.

// RUN: %dexter_regression_test_cxx_build %s -o %t
// RUN: %dexter_regression_test_run --binary %t -- %s | FileCheck %s

// CHECK: correct_steps: 5
// CHECK: incorrect_steps: 0

__attribute__((noinline))
int f2(int a) {
    return a * 2; // !dex_label f2_line
}

__attribute__((noinline))
int f1(int b, int c) {
    return b + f2(c); // !dex_label f1_call_f2
}

int main() {
    int d = f2(4);
    int e = f1(d, 10);
}

/*
---
!where {function: f1}:
    !where {function: f2, lines: !label f2_line}:
        !value a: 10
!where {function: main}:
    !where {function: f2, lines: !label f2_line}:
        !value a: 4
!where {function: f2, lines: !label f2_line}:
    !value a: [4, 10]
!where {lines: !label f1_call_f2}:
    !where {lines: !label f2_line}:
        !value a: 10
...
*/
