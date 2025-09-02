// Purpose:
//      Test that a \DexDeclareAddress value can be used to compare the
//      addresses of two local variables that refer to the same address.
//
// RUN: %dexter_regression_test_cxx_build %s -o %t
// RUN: %dexter_regression_test_run --binary %t -- %s | FileCheck %s
// CHECK: expression_address.cpp

int main() {
    int x = 5;
    int &y = x;
    if (x > 2) { // !dex_label start_line
        int z = 3;
        y += z;
    }
    x = 3; // !dex_label test_line
}

/*
---
!where {function: main}:
    !value "&x": !address x_addr
    !value "y": !address x_addr
    !where {lines: 12}: !then continue
    !where {lines: 14}: !then finish
    !value/all locals: yay
...
*/
