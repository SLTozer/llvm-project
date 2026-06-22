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
  friend struct DenseMapInfo<FLIndex<IndexType>>;
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
  bool operator!=(const FLIndex &Other) const { return Index != Other.Index; }

  IndexType asRaw() const {
    return Index;
  }
  static FLIndex fromRaw(IndexType RawIndex) {
    FLIndex Index;
    Index.Index = RawIndex;
    return Index;
  }

  friend inline hash_code hash_value(const FLIndex<IndexType> &Idx) {
    return hash_value(Idx.Index);
  }
};

template <typename IndexType>
struct DenseMapInfo<FLIndex<IndexType>> {
  static unsigned getHashValue(FLIndex<IndexType> DL) {
    return hash_value(DL.Index);
  }

  static bool isEqual(FLIndex<IndexType> LHS, FLIndex<IndexType> RHS) {
    return LHS.Index == RHS.Index;
  }
};

struct FLInlinedCall {
  FLIndex<uint32_t> SrcLocIdx;
  FLIndex<uint16_t> InlinedAtIdx;
  uint16_t MaxAtomGroup;
  TrackingMDNodeRef InlineeFLMD;
  FLInlinedCall() = default;
  FLInlinedCall(FLIndex<uint32_t> SrcLocIdx, FLIndex<uint16_t> InlinedAtIdx, MDNode *InlineeFLMD)
    : SrcLocIdx(SrcLocIdx), InlinedAtIdx(InlinedAtIdx), InlineeFLMD(InlineeFLMD) {}
  DIFunctionLocalMetadata *getInlinee() const {
    return cast<DIFunctionLocalMetadata>(InlineeFLMD);
  }
  std::pair<uint64_t, DIFunctionLocalMetadata*> asRawParts() const {
    uint64_t Result = (uint64_t)SrcLocIdx.asRaw() << 32;
    Result |= (uint64_t)InlinedAtIdx.asRaw() << 16;
    Result |= MaxAtomGroup;
    return {Result, getInlinee()};
  }
  static FLInlinedCall fromRawParts(uint64_t RawInt, DIFunctionLocalMetadata *Inlinee) {
    FLInlinedCall Result;
    Result.SrcLocIdx = FLIndex<uint32_t>::fromRaw(RawInt >> 32);
    Result.InlinedAtIdx = FLIndex<uint16_t>::fromRaw(RawInt >> 16);
    Result.MaxAtomGroup = RawInt;
    return Result;
  }
};

/// Unique FLMD.
/// Stores source location information.
struct FLSrcLoc {
  uint32_t Line;
  uint16_t Column;
  FLIndex<uint16_t> ScopeIdx;
  FLSrcLoc() = default;
  FLSrcLoc(uint32_t Line, uint16_t Column, FLIndex<uint16_t> ScopeIdx) : Line(Line), Column(Column), ScopeIdx(ScopeIdx) {
    assert(ScopeIdx && "SrcLoc needs valid scope!");
  }
  uint64_t asRawInt() const {
    static_assert(sizeof(*this) == sizeof(uint64_t));
    uint64_t Result;
    std::memcpy(&Result, this, sizeof(Result));
    return Result;
  }
  static FLSrcLoc fromRawInt(uint64_t RawInt) {
    FLSrcLoc Result;
    std::memcpy(&Result, &RawInt, sizeof(Result));
    return Result;
  }
};

/// Unique FLMD, just a wrapper around a DILocalScope.
struct FLScope {
  TrackingMDNodeRef Scope;
  FLScope() = default;
  FLScope(MDNode *Scope) : Scope(Scope) {}
  FLScope(DILocalScope *Scope);
  operator DILocalScope*();
  DILocalScope *get();
  operator const DILocalScope*() const;
  const DILocalScope *get() const;
};

struct FLLoop {
  FLIndex<uint32_t> StartSrcLocIdx;
  FLIndex<uint32_t> EndSrcLocIdx;
  FLIndex<uint16_t> StartInlinedAtIdx;
  FLIndex<uint16_t> EndInlinedAtIdx;
  TrackingMDNodeRef Properties;
  FLLoop() = default;
  FLLoop(FLIndex<uint32_t> StartSrcLocIdx, FLIndex<uint32_t> EndSrcLocIdx, FLIndex<uint16_t> InlinedAtIdx, MDNodeArray Properties);
  FLLoop(FLIndex<uint32_t> StartSrcLocIdx, FLIndex<uint32_t> EndSrcLocIdx, FLIndex<uint16_t> InlinedAtIdx, MDNode *Properties)
    : StartSrcLocIdx(StartSrcLocIdx), EndSrcLocIdx(EndSrcLocIdx), StartInlinedAtIdx(InlinedAtIdx), EndInlinedAtIdx(InlinedAtIdx), Properties(Properties) {}
  MDNodeArray getProperties() const {
    return cast<MDTuple>(Properties);
  }
  std::tuple<uint64_t, uint64_t, MDNode*> asRawParts() const {
    uint64_t SrcLocResult = (uint64_t)StartSrcLocIdx.asRaw() << 32;
    SrcLocResult |= (uint64_t)EndSrcLocIdx.asRaw();
    uint64_t InlinedResult = (uint64_t)StartInlinedAtIdx.asRaw() << 16;
    InlinedResult |= (uint64_t)EndInlinedAtIdx.asRaw();
    return {SrcLocResult, InlinedResult, Properties.get()};
  }
  static FLLoop fromRawParts(uint64_t SrcLocPart, uint64_t InlinedPart, MDNode *PropertiesPart) {
    FLLoop Result;
    Result.StartSrcLocIdx = FLIndex<uint32_t>::fromRaw(SrcLocPart >> 32);
    Result.EndSrcLocIdx = FLIndex<uint32_t>::fromRaw(SrcLocPart);
    Result.StartInlinedAtIdx = FLIndex<uint16_t>::fromRaw(InlinedPart >> 16);
    Result.EndInlinedAtIdx = FLIndex<uint16_t>::fromRaw(InlinedPart);
    Result.Properties = TrackingMDNodeRef(PropertiesPart);
    return Result;
  }
};




/// Builder class to perform the initial population for FLMD.
/// Besides allowing direct modification of arrays that normally have a limited
/// interface, this also ensures that some of the elements that are required to
/// appear at a fixed position in the array  
/// TODO: Merge this into DIBuilder.
class FLMDBuilder {
public:
  SmallVector<FLScope, 0> Scopes;
  DenseMap<DILocalScope*, FLIndex<uint16_t>> ScopeMap;
  SmallVector<FLSrcLoc, 0> SrcLocs;
  DenseMap<std::tuple<uint32_t, uint16_t, DILocalScope*>, FLIndex<uint32_t>> SrcLocMap;
  SmallVector<FLInlinedCall, 0> InlinedCalls;
  SmallVector<FLLoop, 0> Loops;
  SmallDenseMap<class Instruction *, uint16_t> InstrLoops;

  FLIndex<uint16_t> addScope(DILocalScope* Scope) {
    if (auto ScopeIt = ScopeMap.find(Scope); ScopeIt != ScopeMap.end())
      return ScopeIt->second;
    Scopes.push_back(FLScope{Scope});
    return Scopes.size() - 1;
  }
  FLIndex<uint32_t> addSrcLoc(uint32_t Line, uint16_t Column, DILocalScope* Scope) {
    if (auto SrcLocIt = SrcLocMap.find({Line, Column, Scope}); SrcLocIt != SrcLocMap.end())
      return SrcLocIt->second;
    FLIndex<uint16_t> ScopeIdx = addScope(Scope);
    SrcLocs.push_back(FLSrcLoc(Line, Column, ScopeIdx));
    return SrcLocs.size() - 1;
  }
  FLMDBuilder(const DISubprogram *SP);
};

/// Storage class for function-local metadata objects.
/// TODO: Figure out how to divide this class and the actual FLMD types up among
/// existing headers.
class DIFunctionLocalMetadata : public MDNode {
  DIFunctionLocalMetadata(LLVMContext &C, StorageType Storage) : MDNode(C, DIFunctionLocalMetadataKind, Storage, {}) {}
  ~DIFunctionLocalMetadata() = default;
public:
  friend class LLVMContextImpl;
  friend class MDNode;
  SmallVector<FLScope, 0> Scopes;
  SmallVector<FLSrcLoc, 0> SrcLocs;
  SmallVector<FLInlinedCall, 0> InlinedCalls;
  SmallVector<FLLoop, 0> Loops;
  SmallDenseMap<class Instruction *, uint16_t> InstrLoops;

  // FIXME: FLMD is a funny case where it takes no arguments and can only be
  // created Distinct. Decide later whether this needs to change.
  static DIFunctionLocalMetadata *getDistinct(LLVMContext &Context);
  static TempDIFunctionLocalMetadata getTemporary(LLVMContext &Context);
  TempDIFunctionLocalMetadata cloneImpl() const {
    return getTemporary(getContext());
  }

  void build(FLMDBuilder &Builder) {
    assert(Scopes.empty() && SrcLocs.empty() && InlinedCalls.empty() && Loops.empty() && InstrLoops.empty() && "Can't use builder on an already-created FLMD!");
    Scopes = Builder.Scopes;
    SrcLocs = Builder.SrcLocs;
    InlinedCalls = Builder.InlinedCalls;
    Loops = Builder.Loops;
    InstrLoops = Builder.InstrLoops;
  }

  FLScope getScope(FLIndex<uint16_t> Idx) const {
    return Scopes[Idx.get()];
  }
  FLSrcLoc getSrcLoc(FLIndex<uint32_t> Idx) const {
    return SrcLocs[Idx.get()];
  }
  FLInlinedCall getInlinedCall(FLIndex<uint16_t> Idx) const {
    return InlinedCalls[Idx.get()];
  }
  FLLoop getLoop(FLIndex<uint32_t> Idx) const {
    return Loops[Idx.get()];
  }

  FLIndex<uint16_t> getFLScopeIdx(DILocalScope *Scope) {
    for (uint16_t Idx = 0; Idx < Scopes.size(); ++Idx)
      if (Scopes[Idx] == Scope)
        return Idx;
    Scopes.push_back(FLScope(Scope));
    return Scopes.size() - 1;
  }

  FLIndex<uint32_t> getFLSrcLocIdx(uint32_t Line, uint16_t Column, FLIndex<uint16_t> ScopeIdx) {
    for (uint32_t Idx = 0; Idx < SrcLocs.size(); ++Idx) {
      FLSrcLoc &SrcLoc = SrcLocs[Idx];
      if (SrcLoc.Line == Line && SrcLoc.Column == Column && SrcLoc.ScopeIdx == ScopeIdx)
        return Idx;
    }
    SrcLocs.push_back(FLSrcLoc(Line, Column, ScopeIdx));
    return SrcLocs.size() - 1;
  }
  FLIndex<uint32_t> getFLSrcLocIdx(uint32_t Line, uint16_t Column, DILocalScope *Scope) {
    return getFLSrcLocIdx(Line, Column, getFLScopeIdx(Scope));
  }
  FLIndex<uint16_t> addInlinedCall(FLInlinedCall InlinedCall) {
    InlinedCalls.push_back(InlinedCall);
    return InlinedCalls.size() - 1;
  }
};

} // end namespace llvm


#endif // LLVM_IR_FUNCTIONLOCALMETADATA_H
