// RUN: mlir-opt %s -test-affine-reify-value-bounds -verify-diagnostics \
// RUN:     -split-input-file | FileCheck %s

// CHECK: #[[$map:.*]] = affine_map<()[s0, s1] -> (s0 + s1)>
// CHECK-LABEL: func @affine_apply(
//  CHECK-SAME:     %[[a:.*]]: index, %[[b:.*]]: index
//       CHECK:   %[[apply:.*]] = affine.apply #[[$map]]()[%[[a]], %[[b]]]
//       CHECK:   %[[apply:.*]] = affine.apply #[[$map]]()[%[[a]], %[[b]]]
//       CHECK:   return %[[apply]]
func.func @affine_apply(%a: index, %b: index) -> index {
  %0 = affine.apply affine_map<()[s0, s1] -> (s0 + s1)>()[%a, %b]
  %1 = "test.reify_bound"(%0) : (index) -> (index)
  return %1 : index
}

// -----

// CHECK-LABEL: func @affine_max_lb(
//  CHECK-SAME:     %[[a:.*]]: index
//       CHECK:   %[[c2:.*]] = arith.constant 2 : index
//       CHECK:   return %[[c2]]
func.func @affine_max_lb(%a: index) -> (index) {
  // Note: There are two LBs: s0 and 2. FlatAffineValueConstraints always
  // returns the constant one at the moment.
  %1 = affine.max affine_map<()[s0] -> (s0, 2)>()[%a]
  %2 = "test.reify_bound"(%1) {type = "LB"}: (index) -> (index)
  return %2 : index
}

// -----

func.func @affine_max_ub(%a: index) -> (index) {
  %1 = affine.max affine_map<()[s0] -> (s0, 2)>()[%a]
  // expected-error @below{{could not reify bound}}
  %2 = "test.reify_bound"(%1) {type = "UB"}: (index) -> (index)
  return %2 : index
}

// -----

// CHECK-LABEL: func @affine_min_ub(
//  CHECK-SAME:     %[[a:.*]]: index
//       CHECK:   %[[c3:.*]] = arith.constant 3 : index
//       CHECK:   return %[[c3]]
func.func @affine_min_ub(%a: index) -> (index) {
  // Note: There are two UBs: s0 + 1 and 3. FlatAffineValueConstraints always
  // returns the constant one at the moment.
  %1 = affine.min affine_map<()[s0] -> (s0, 2)>()[%a]
  %2 = "test.reify_bound"(%1) {type = "UB"}: (index) -> (index)
  return %2 : index
}

// -----

func.func @affine_min_lb(%a: index) -> (index) {
  %1 = affine.min affine_map<()[s0] -> (s0, 2)>()[%a]
  // expected-error @below{{could not reify bound}}
  %2 = "test.reify_bound"(%1) {type = "LB"}: (index) -> (index)
  return %2 : index
}

// -----

// CHECK-LABEL: func @composed_affine_apply(
//       CHECK:   %[[cst:.*]] = arith.constant -8 : index
//       CHECK:   return %[[cst]]
func.func @composed_affine_apply(%i1 : index) -> (index) {
  // The ValueBoundsOpInterface implementation of affine.apply fully composes
  // the affine map (and its operands) with other affine.apply ops drawn from
  // its operands before adding it to the constraint set. This is to work
  // around a limitation in `FlatLinearConstraints`, which can currently not
  // compute a constant bound for %s. (The affine map simplification logic can
  // simplify %s to -8.)
  %i2 = affine.apply affine_map<(d0) -> ((d0 floordiv 32) * 16)>(%i1)
  %i3 = affine.apply affine_map<(d0) -> ((d0 floordiv 32) * 16 + 8)>(%i1)
  %s = affine.apply affine_map<()[s0, s1] -> (s0 - s1)>()[%i2, %i3]
  %reified = "test.reify_bound"(%s) {type = "EQ", constant} : (index) -> (index)
  return %reified : index
}


// -----

func.func @are_equal(%i1 : index) {
  %i2 = affine.apply affine_map<(d0) -> ((d0 floordiv 32) * 16)>(%i1)
  %i3 = affine.apply affine_map<(d0) -> ((d0 floordiv 32) * 16 + 8)>(%i1)
  %s = affine.apply affine_map<()[s0, s1] -> (s0 - s1)>()[%i2, %i3]
  // expected-remark @below{{false}}
   "test.compare"(%i2, %i3) : (index, index) -> ()
  return
}

// -----

// Test for affine::fullyComposeAndCheckIfEqual
func.func @composed_are_equal(%i1 : index) {
  %i2 = affine.apply affine_map<(d0) -> ((d0 floordiv 32) * 16)>(%i1)
  %i3 = affine.apply affine_map<(d0) -> ((d0 floordiv 32) * 16 + 8)>(%i1)
  %s = affine.apply affine_map<()[s0, s1] -> (s0 - s1)>()[%i2, %i3]
  // expected-remark @below{{different}}
   "test.compare"(%i2, %i3) {compose} : (index, index) -> ()
  return
}

// -----

func.func @compare_affine_max(%a: index, %b: index) {
  %0 = affine.max affine_map<()[s0, s1] -> (s0, s1)>()[%a, %b]
  // expected-remark @below{{true}}
  "test.compare"(%0, %a) {cmp = "GE"} : (index, index) -> ()
  // expected-error @below{{unknown}}
  "test.compare"(%0, %a) {cmp = "GT"} : (index, index) -> ()
  // expected-remark @below{{false}}
  "test.compare"(%0, %a) {cmp = "LT"} : (index, index) -> ()
  // expected-error @below{{unknown}}
  "test.compare"(%0, %a) {cmp = "LE"} : (index, index) -> ()
  return
}

// -----

func.func @compare_affine_min(%a: index, %b: index) {
  %0 = affine.min affine_map<()[s0, s1] -> (s0, s1)>()[%a, %b]
  // expected-error @below{{unknown}}
  "test.compare"(%0, %a) {cmp = "GE"} : (index, index) -> ()
  // expected-remark @below{{false}}
  "test.compare"(%0, %a) {cmp = "GT"} : (index, index) -> ()
  // expected-error @below{{unknown}}
  "test.compare"(%0, %a) {cmp = "LT"} : (index, index) -> ()
  // expected-remark @below{{true}}
  "test.compare"(%0, %a) {cmp = "LE"} : (index, index) -> ()
  return
}

// -----

func.func @compare_const_map() {
  %c5 = arith.constant 5 : index
  // expected-remark @below{{true}}
  "test.compare"(%c5) {cmp = "GT", rhs_map = affine_map<() -> (4)>}
      : (index) -> ()
  // expected-remark @below{{true}}
  "test.compare"(%c5) {cmp = "LT", lhs_map = affine_map<() -> (4)>}
      : (index) -> ()
  return
}

// -----

func.func @compare_maps(%a: index, %b: index) {
  // expected-remark @below{{true}}
  "test.compare"(%a, %b, %b, %a)
      {cmp = "GT", lhs_map = affine_map<(d0, d1) -> (1 + d0 + d1)>,
       rhs_map = affine_map<(d0, d1) -> (d0 + d1)>}
      : (index, index, index, index) -> ()
  return
}
