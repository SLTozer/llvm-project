// Tests that nested !where blocks are properly constrained by their parent !where blocks.

// RUN: %dexter_regression_test_cxx_build %s -o %t
// RUN: %dexter_regression_test_run --binary %t -- %s | FileCheck %s

// CHECK: correct_steps: 4
// CHECK: incorrect_steps: 0

__attribute__((noinline)) void foo(int) {}

int main() {
    int total = 0;
    for (int i = 0; i < 10; ++i) {
        total += i;
        foo(total); // !dex_label loop_line
    }
}

/*
---
!where {function: main}:
    !where {lines: !label loop_line, conditions: "i >= 3 && i < 7"}:
        !value total: [6, 10, 15, 21]
...
*/
