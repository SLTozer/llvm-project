//===- llvm/IR/OptBisect/Bisect.cpp - LLVM Bisect support -----------------===//
//
// Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
//
//===----------------------------------------------------------------------===//
//
/// \file
/// This file implements support for a bisecting optimizations based on a
/// command line option.
//
//===----------------------------------------------------------------------===//

#include "llvm/IR/OptBisect.h"
#include "llvm/Config/config.h"
#include "llvm/Pass.h"
#include "llvm/Support/CommandLine.h"
#include "llvm/Support/raw_ostream.h"
#include <cassert>

using namespace llvm;

static OptBisect &getOptBisector() {
  static OptBisect OptBisector;
  return OptBisector;
}

namespace {
#ifdef LLVM_ENABLE_DEBUGLOC_ORIGIN_TRACKING
// When origin tracking is enabled, we choose to set OptBisect to "-1" by
// default and to run in quiet mode. This means that it will not stop any
// optimizations or produce any output, but it will be enabled and continue to
// count optimizations, which we use in the debugify reports.
constexpr int DefaultLimit = -1;
constexpr bool DefaultVerbose = false;
#else
// In normal builds, we disable OptBisect by default and produce verbose output.
constexpr int DefaultLimit = OptBisect::Disabled;
constexpr bool DefaultVerbose = true;
#endif
}

static cl::opt<int> OptBisectLimit("opt-bisect-limit", cl::Hidden,
                                   cl::init(DefaultLimit), cl::Optional,
                                   cl::cb<void, int>([](int Limit) {
                                     getOptBisector().setLimit(Limit);
                                   }),
                                   cl::desc("Maximum optimization to perform"));

static cl::opt<bool> OptBisectVerbose(
    "opt-bisect-verbose",
    cl::desc("Show verbose output when opt-bisect-limit is set"), cl::Hidden,
    cl::init(DefaultVerbose), cl::Optional);

static void printPassMessage(const StringRef &Name, int PassNum,
                             StringRef TargetDesc, bool Running) {
  StringRef Status = Running ? "" : "NOT ";
  errs() << "BISECT: " << Status << "running pass "
         << "(" << PassNum << ") " << Name << " on " << TargetDesc << "\n";
}

bool OptBisect::shouldRunPass(const StringRef PassName,
                              StringRef IRDescription) {
  assert(isEnabled());

  int CurBisectNum = ++LastBisectNum;
  bool ShouldRun = (BisectLimit == -1 || CurBisectNum <= BisectLimit);
  if (OptBisectVerbose)
    printPassMessage(PassName, CurBisectNum, IRDescription, ShouldRun);
  return ShouldRun;
}

const int OptBisect::Disabled;

OptPassGate &llvm::getGlobalPassGate() { return getOptBisector(); }
