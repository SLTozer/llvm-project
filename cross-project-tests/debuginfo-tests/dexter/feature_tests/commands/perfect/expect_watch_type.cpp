// Purpose:
//      Check that \DexExpectWatchType applies no penalties when expected
//      types are found.
//
// UNSUPPORTED: system-darwin
//
// TODO: On Windows WITH dbgeng, This test takes a long time to run and doesn't evaluate type values
// in the same manner as LLDB.
// XFAIL: system-windows
//
// RUN: %dexter_regression_test_cxx_build %s -o %t
// RUN: %dexter_regression_test_run --binary %t -- %s | FileCheck %s
// CHECK: expect_watch_type.cpp:

template<class T>
class Doubled {
public:
  Doubled(const T & to_double)
    : m_member(to_double * 2) {}

  T GetVal() {
    T to_return = m_member; // !dex_label gv_start
    return to_return;       // !dex_label gv_end
  }

  static T static_doubler(const T & to_double) {
    T result = 0;           // !dex_label sd_start
    result = to_double * 2;
    return result;          // !dex_label sd_end
  }

private:
  T m_member;
};

int main() {
  auto myInt = Doubled<int>(5); // !dex_label main_start
  auto myDouble = Doubled<double>(5.5);
  auto staticallyDoubledInt = Doubled<int>::static_doubler(5);
  auto staticallyDoubledDouble = Doubled<double>::static_doubler(5.5);
  return int(double(myInt.GetVal())
         + double(staticallyDoubledInt)
         + myDouble.GetVal()
         + staticallyDoubledDouble); // !dex_label main_end
}

/*
---
!where {lines: !range [22, 23]}:
  !type m_member: [int, double]
!where {lines: !range [27, 29]}:
  !type to_double: [const int &, const double &]
!where {lines: !range [37, 44]}:
  !type myInt                   : Doubled<int>
  !type myDouble                : Doubled<double>
  !type staticallyDoubledInt    : int
  !type staticallyDoubledDouble : double
...
*/

