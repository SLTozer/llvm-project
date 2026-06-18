//===- DebugLoc.h - Debug Location Information ------------------*- C++ -*-===//
//
// Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
//
//===----------------------------------------------------------------------===//
//
// This file defines a number of light weight data structures used
// to describe and track debug location information.
//
//===----------------------------------------------------------------------===//

#ifndef LLVM_IR_FUNCTIONLOCALMETADATA_H
#define LLVM_IR_FUNCTIONLOCALMETADATA_H

#include "llvm/ADT/DenseMap.h"
#include "llvm/Config/llvm-config.h"
#include "llvm/IR/ModuleSlotTracker.h"
#include "llvm/IR/PseudoProbe.h"
#include "llvm/IR/TrackingMDRef.h"
#include "llvm/Support/CommandLine.h"
#include "llvm/Support/Compiler.h"
#include "llvm/Support/DataTypes.h"
#include "llvm/Support/Discriminator.h"
#include <cstddef>
#include <functional>
#include <optional>

namespace llvm {

class DILocalScope;
class MDTuple;
class DIFunctionLocalMetadata;

/// Small wrapper class for an FLMD index, which may be "no index".
/// Should be checked to see if value is present before using, otherwise the
/// implicit/explicit index value will be invalid.
/// Internally uses 0 as the "no index" value, and stores the internal index value as the
/// actual index + 1, subtracting to get the real index.
template <typename IndexType>
class FLIndex {
    IndexType Index;
public:
    FLIndex() : Index(0) {}
    FLIndex(IndexType InIndex) : Index(InIndex + 1) {
      assert(InIndex < std::numeric_limits<IndexType>::max() && "Hit maximum index limit!");
    }
    operator bool() const {
        return Index;
    }
    IndexType get() const {
        return Index - 1;
    }
    operator IndexType() const {
        return get();
    }
    bool operator==(const FLIndex &Other) const { return Index == Other.Index; }
};

struct FLInlinedCall {
  FLIndex<uint32_t> SrcLocIdx;
  FLIndex<uint16_t> InlinedAtIdx;
  uint16_t MaxAtomGroup;
  DIFunctionLocalMetadata *InlineeFLMD;
};

/// Unique FLMD.
/// Stores source location information.
struct FLSrcLoc {
  uint32_t Line;
  uint16_t Column;
  FLIndex<uint16_t> ScopeIdx;
  FLSrcLoc(uint32_t Line, uint16_t Column, FLIndex<uint16_t> ScopeIdx) : Line(Line), Column(Column), ScopeIdx(ScopeIdx) {
    assert(ScopeIdx && "SrcLoc needs valid scope!");
  }
};

/// Unique FLMD, just a wrapper around a DILocalScope.
struct FLScope {
  DILocalScope *Scope;
  FLScope(DILocalScope *Scope) : Scope(Scope) {}
};

struct FLLoop {
  FLIndex<uint32_t> StartSrcLocIdx;
  FLIndex<uint32_t> EndSrcLocIdx;
  FLIndex<uint16_t> StartInlinedAtIdx;
  FLIndex<uint16_t> EndInlinedAtIdx;
  MDNodeArray Properties;

  FLDebugLoc getStartLoc() {
    if (!StartSrcLocIdx)
      return FLDebugLoc();
    return FLDebugLoc(StartSrcLocIdx, )
  }
};


} // end namespace llvm


#endif // LLVM_IR_FUNCTIONLOCALMETADATA_H
