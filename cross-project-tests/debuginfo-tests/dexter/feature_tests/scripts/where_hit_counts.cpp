// Tests that nested !where blocks are properly constrained by their parent !where blocks.

// RUN: %dexter_regression_test_cxx_build %s -o %t
// RUN: %dexter_regression_test_run --binary %t -- %s | FileCheck %s

// CHECK: correct_steps: 20
// CHECK: incorrect_steps: 0

__attribute__((noinline)) int foo(int a) {
    int result = a * 2;
    return result; // !dex_label foo_line
}

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
    !where {lines: !label loop_line, for_hit_count: 3}:
        !value total: [0, 1, 3]
    !where {lines: !label loop_line, for_hit_count: 4, after_hit_count: 3}:
        !value total: [6, 10, 15, 21]
    !where {lines: !label loop_line, after_hit_count: 7}:
        !value total: [28, 36, 45]
    !where {lines: !label loop_line}:
        !value total: [0, 1, 3, 6, 10, 15, 21, 28, 36, 45]
    !where {function: foo, for_hit_count: 3}:
        !where {lines: !label foo_line}:
            !value result: [0, 2, 6]
    !where {function: foo, for_hit_count: 4, after_hit_count: 3}:
        !where {lines: !label foo_line}:
            !value result: [12, 20, 30, 42]
    !where {function: foo, after_hit_count: 7}:
        !where {lines: !label foo_line}:
            !value result: [56, 72, 90]
...
*/
