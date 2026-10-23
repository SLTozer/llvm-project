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

#include "llvm/ADT/ArrayRef.h"
#include "llvm/ADT/DenseMap.h"
#include "llvm/ADT/DenseSet.h"
#include "llvm/ADT/Hashing.h"
#include "llvm/ADT/SmallVector.h"
#include "llvm/Config/llvm-config.h"
#include "llvm/IR/ModuleSlotTracker.h"
#include "llvm/IR/PseudoProbe.h"
#include "llvm/IR/TrackingMDRef.h"
#include "llvm/Support/CommandLine.h"
#include "llvm/Support/Compiler.h"
#include "llvm/Support/DataTypes.h"
#include "llvm/Support/Discriminator.h"
#include <cstddef>
#include <cstdint>
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
  void addOffset(IndexType Offset) {
    if (*this)
      Index += Offset;
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
  uint16_t MaxAtomGroup : 15;
  uint16_t Uniquable : 1;
  MDNode *InlineeFLMD;
  FLInlinedCall() = default;
  FLInlinedCall(
      FLIndex<uint32_t> SrcLocIdx, FLIndex<uint16_t> InlinedAtIdx,
      MDNode *InlineeFLMD, bool Uniquable, uint16_t MaxAtomGroup = 0)
      : SrcLocIdx(SrcLocIdx), InlinedAtIdx(InlinedAtIdx),
        MaxAtomGroup(MaxAtomGroup), Uniquable(Uniquable),
        InlineeFLMD(InlineeFLMD) {
    assert(MaxAtomGroup < 0x8000 && "Max Atom group too large for bitfield!");
  }
  DIFunctionLocalMetadata *getInlinee() const {
    return cast<DIFunctionLocalMetadata>(InlineeFLMD);
  }
  std::pair<uint64_t, DIFunctionLocalMetadata*> asRawParts() const {
    uint64_t Result = (uint64_t)SrcLocIdx.asRaw() << 32;
    Result |= (uint64_t)InlinedAtIdx.asRaw() << 16;
    Result |= (uint64_t)MaxAtomGroup << 1;
    Result |= Uniquable;
    return {Result, getInlinee()};
  }
  static FLInlinedCall fromRawParts(uint64_t RawInt, DIFunctionLocalMetadata *Inlinee);
  uint16_t getNewAtomGroup() {
    // FIXME: Remove this assert later, it's not really a problem if atom groups
    // wrap - but we probably want to wrap straight to 1 rather than 0, and we
    // also want to know if this trips regularly during development.
    assert(MaxAtomGroup < 0x7fff && "Atom group unexpectedly wrapped!");
    return ++MaxAtomGroup;
  }
  // Equality check that ignores MaxAtomGroup, used for uniquing.
  bool isEquivalent(const FLInlinedCall &Other) const {
    return SrcLocIdx == Other.SrcLocIdx
      && InlinedAtIdx == Other.InlinedAtIdx
      && Uniquable == Other.Uniquable
      && InlineeFLMD == Other.InlineeFLMD;
  }
  // Hash of the fields compared by isEquivalent.
  unsigned getHash() const {
    uint64_t Raw = (uint64_t)SrcLocIdx.asRaw() << 32 |
                   (uint64_t)InlinedAtIdx.asRaw() << 16 | Uniquable;
    return static_cast<unsigned>(size_t(hash_combine(Raw, InlineeFLMD)));
  }
  // FIXME: We should really ignore MaxAtomGroup for some/most/all equality
  //        comparisons, but exactly how we handle that field during e.g.
  //        uniquing may not be as simple as ignoring it.
  bool operator==(const FLInlinedCall &Other) const {
    return asRawParts() == Other.asRawParts();
  }
  bool operator!=(const FLInlinedCall &Other) const {
    return asRawParts() != Other.asRawParts();
  }

  friend inline hash_code hash_value(const FLInlinedCall &IC) {
    return hash_value(IC.asRawParts());
  }
};
template<>
struct DenseMapInfo<FLInlinedCall> {
  static unsigned getHashValue(FLInlinedCall IC) {
    return hash_value(IC);
  }

  static bool isEqual(FLInlinedCall LHS, FLInlinedCall RHS) {
    return LHS == RHS;
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
  bool operator==(const FLSrcLoc &Other) {
    return std::tie(Line, Column, ScopeIdx) ==
      std::tie(Other.Line, Other.Column, Other.ScopeIdx);
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
  bool isEquivalent(const FLSrcLoc &Other) const {
    return asRawInt() == Other.asRawInt();
  }
  unsigned getHash() const {
    return static_cast<unsigned>(size_t(hash_value(asRawInt())));
  }
  friend inline hash_code hash_value(const FLSrcLoc &SrcLoc) {
    return hash_value(SrcLoc.asRawInt());
  }
};
template<>
struct DenseMapInfo<FLSrcLoc> {
  static unsigned getHashValue(FLSrcLoc SrcLoc) {
    return hash_value(SrcLoc);
  }

  static bool isEqual(FLSrcLoc LHS, FLSrcLoc RHS) {
    return LHS == RHS;
  }
};

/// Unique FLMD, just a wrapper around a DILocalScope.
struct FLScope {
  MDNode *Scope;
  FLScope() = default;
  FLScope(MDNode *Scope) : Scope(Scope) {}
  FLScope(DILocalScope *Scope);
  operator DILocalScope*();
  bool operator==(const FLScope &Other) {
    return Scope == Other.Scope;
  }
  DILocalScope *get();
  operator const DILocalScope*() const;
  const DILocalScope *get() const;
  friend inline hash_code hash_value(const FLScope &Scope) {
    return hash_value(Scope.Scope);
  }
};
template<>
struct DenseMapInfo<FLScope> {
  static unsigned getHashValue(FLScope Scope) {
    return hash_value(Scope);
  }

  static bool isEqual(FLScope LHS, FLScope RHS) {
    return LHS == RHS;
  }
};

struct FLLoop {
  FLIndex<uint32_t> StartSrcLocIdx;
  FLIndex<uint32_t> EndSrcLocIdx;
  FLIndex<uint16_t> StartInlinedAtIdx;
  FLIndex<uint16_t> EndInlinedAtIdx;
  MDNode *Properties;
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
    return {SrcLocResult, InlinedResult, Properties};
  }
  static FLLoop fromRawParts(uint64_t SrcLocPart, uint64_t InlinedPart, MDNode *PropertiesPart) {
    FLLoop Result;
    Result.StartSrcLocIdx = FLIndex<uint32_t>::fromRaw(SrcLocPart >> 32);
    Result.EndSrcLocIdx = FLIndex<uint32_t>::fromRaw(SrcLocPart);
    Result.StartInlinedAtIdx = FLIndex<uint16_t>::fromRaw(InlinedPart >> 16);
    Result.EndInlinedAtIdx = FLIndex<uint16_t>::fromRaw(InlinedPart);
    Result.Properties = PropertiesPart;
    return Result;
  }
};



/// An FLSrcLoc with external references (i.e. the ScopeIdx) resolved and
/// replaced with the underlying data (up to the metadata pointers only), such
/// that no further FLMD lookups/context are necessary.
struct ResolvedFLSrcLoc {
  uint32_t Line;
  uint16_t Column;
  DILocalScope *Scope;
};

/// An FLInlinedCall with external references resolved and replaced with the
/// underlying data (up to the metadata pointers only), such that no further
/// FLMD lookups/context are necessary.
/// The full chain of inlined calls are stored as a linked list of
/// ResolvedFLInlinedCalls.
/// Even though references are resolved, we still store the index of every
/// FLInlinedCall, because it forms a part of the inlined call's unique
/// identity, which logically distinguishes it from other inlined calls with
/// identical data fields.
struct ResolvedFLInlinedCall {
  ResolvedFLSrcLoc SrcLoc;
  uint16_t SelfIndex;
  uint16_t MaxAtomGroup : 15;
  uint16_t Uniquable : 1;
  std::unique_ptr<ResolvedFLInlinedCall> InlinedAt;

  bool isSame(const ResolvedFLInlinedCall &Other) {
    return SelfIndex == Other.SelfIndex;
  }
};


/// Uniquing index for table entries: each bucket holds (hash << 32 | index) so
/// the set needs no access to the table when it grows.
template <typename EntryT> struct FLEntryIndexInfo {
  struct Key {
    const EntryT &Entry;
    ArrayRef<EntryT> Table;
    unsigned Hash;
  };
  static uint64_t getEmptyKey() { return ~0ULL; }
  static uint64_t getTombstoneKey() { return ~0ULL - 1; }
  static unsigned getHashValue(uint64_t V) { return V >> 32; }
  static unsigned getHashValue(const Key &K) { return K.Hash; }
  static bool isEqual(uint64_t LHS, uint64_t RHS) { return LHS == RHS; }
  static bool isEqual(const Key &K, uint64_t V) {
    if (V >= getTombstoneKey() || (V >> 32) != K.Hash)
      return false;
    return K.Table[uint32_t(V)].isEquivalent(K.Entry);
  }
};
template <typename EntryT>
using FLEntryIndex = DenseSet<uint64_t, FLEntryIndexInfo<EntryT>>;

/// Storage class for function-local metadata objects.
/// TODO: Figure out how to divide this class and the actual FLMD types up among
/// existing headers.
class DIFunctionLocalMetadata : public MDNode {
  DIFunctionLocalMetadata(LLVMContext &C, StorageType Storage) : MDNode(C, DIFunctionLocalMetadataKind, Storage, {}) {}
  ~DIFunctionLocalMetadata() = default;

  // Uniquing indexes for Scopes, SrcLocs and InlinedCalls. If a table holds
  // duplicate entries, the index refers to the first of them.
  DenseMap<const MDNode *, uint16_t> ScopeIndex;
  FLEntryIndex<FLSrcLoc> SrcLocIndex;
  // Uniquable inlined calls only; distinct calls are never found by lookup.
  FLEntryIndex<FLInlinedCall> UniquedInlinedCallIndex;

public:
  // These are 3 fixed values inserted into every DIFunctionLocalMetadata with
  // source locations, corresponding to "special" locations that we might select
  // for "compiler-generated" instructions at some point.
  enum {
    LineZeroSrcLocIdx = 0,
    SPLineSrcLocIdx = 1,
    SPScopeLineSrcLocIdx = 2,
    FirstNormalSrcLoxIdx = 3,
  };
  friend class LLVMContextImpl;
  friend class MDNode;
  // Scopes, SrcLocs and InlinedCalls must only be extended through the
  // get/add/append methods below, which keep the uniquing indexes up to date.
  // After changing the Scope or InlineeFLMD of an existing entry in place, call
  // rebuildUniquingIndexes().
  SmallVector<FLScope, 0> Scopes;
  SmallVector<FLSrcLoc, 0> SrcLocs;
  SmallVector<FLInlinedCall, 0> InlinedCalls;
  SmallVector<FLLoop, 0> Loops;
  SmallDenseMap<class Instruction *, uint16_t> InstrLoops;
  // TODO: Move this to Subclassdata.
  uint16_t MaxAtomGroup = 0;
  // If this is true, then this is a special FLContext, used for a function
  // without debug info to store inlined call information. This FLContext
  // contains no Scopes and no SrcLocs, meaning it is never valid to create a
  // non-inlined debug loc within it.
  // Nested InlinedCalls are copied during inlining as normal, and the resulting
  // InlinedCall for the inlining operation has no SrcLoc and no InlinedAt; this
  // requires some special handling for functions like "getInlinedAtLocation"
  // that explicitly traverse the InlinedAt chain. If this function is then
  // inlined into a debug function, the location-less InlinedCall is overwritten
  // instead of transferred.
  // NB: Hopefully this design doesn't raise many problems as-is, because in
  // general we only care about debug locs inlined into a nodebug function when
  // they are inlined again into a debug function - otherwise they are generally
  // ignored. If this leads to problems, then we need a more sophisticated
  // solution.
  bool IsNonDebugFn = false;

  // FIXME: FLMD is a funny case where it takes no arguments and can only be
  // created Distinct. Decide later whether this needs to change.
  static DIFunctionLocalMetadata *getDistinct(LLVMContext &Context);
  static TempDIFunctionLocalMetadata getTemporary(LLVMContext &Context);
  TempDIFunctionLocalMetadata clone() const { return cloneImpl(); }
  TempDIFunctionLocalMetadata cloneImpl() const {
    llvm_unreachable("Does this make any sense?");
  }

  // TODO: Figure out the ergonomics of this.
  bool isNonDebug() {
    return IsNonDebugFn;
  }
  void setNonDebug() {
    IsNonDebugFn = true;
  }

  FLScope getScope(FLIndex<uint16_t> Idx) const {
    return Scopes[Idx.get()];
  }
  FLScope getScope(FLIndex<uint16_t> Idx, FLIndex<uint16_t> InlinedAt) const {
    if (!InlinedAt)
      return Scopes[Idx.get()];
    return InlinedCalls[InlinedAt.get()].getInlinee()->getScope(Idx);
  }
  FLSrcLoc getSrcLoc(FLIndex<uint32_t> Idx) const {
    return SrcLocs[Idx.get()];
  }
  FLSrcLoc getSrcLoc(FLIndex<uint32_t> Idx, FLIndex<uint16_t> InlinedAt) const {
    if (!InlinedAt)
      return SrcLocs[Idx.get()];
    return InlinedCalls[InlinedAt.get()].getInlinee()->getSrcLoc(Idx);
  }
  FLInlinedCall getInlinedCall(FLIndex<uint16_t> Idx) const {
    return InlinedCalls[Idx.get()];
  }
  FLLoop getLoop(FLIndex<uint32_t> Idx) const {
    return Loops[Idx.get()];
  }

  uint16_t getNewAtomGroup(FLIndex<uint16_t> InlinedCallIdx) {
    if (!InlinedCallIdx) {
      // FIXME: See comment in corresponding FLInlinedCall method.
      assert(MaxAtomGroup < 0x7fff && "Atom group unexpectedly wrapped!");
      return ++MaxAtomGroup;
    }
    return InlinedCalls[InlinedCallIdx.get()].getNewAtomGroup();
  }
  void updateAtomGroupWaterline(FLIndex<uint16_t> InlinedCallIdx, uint16_t NewWaterline) {
    assert(NewWaterline <= 0x7fff && "New waterline is too high!");
    if (!InlinedCallIdx)
      MaxAtomGroup = std::max(MaxAtomGroup, NewWaterline);
    else
      InlinedCalls[InlinedCallIdx.get()].MaxAtomGroup = std::max(InlinedCalls[InlinedCallIdx.get()].MaxAtomGroup, NewWaterline);
  }
  uint16_t getAtomGroupWaterline(FLIndex<uint16_t> InlinedCallIdx) {
    if (!InlinedCallIdx)
      return MaxAtomGroup;
    return InlinedCalls[InlinedCallIdx.get()].MaxAtomGroup;
  }

  FLIndex<uint16_t> getFLScopeIdx(DILocalScope *Scope);

  FLIndex<uint32_t> getFLSrcLocIdx(const FLSrcLoc &SrcLoc);
  FLIndex<uint32_t> getFLSrcLocIdx(uint32_t Line, uint16_t Column, FLIndex<uint16_t> ScopeIdx) {
    return getFLSrcLocIdx(FLSrcLoc(Line, Column, ScopeIdx));
  }
  FLIndex<uint32_t> getFLSrcLocIdx(uint32_t Line, uint16_t Column, DILocalScope *Scope) {
    return getFLSrcLocIdx(Line, Column, getFLScopeIdx(Scope));
  }
  /// Returns the existing equivalent inlined call if \p InlinedCall is
  /// uniquable, raising its MaxAtomGroup to that of \p InlinedCall; otherwise
  /// appends a new inlined call.
  FLIndex<uint16_t> addInlinedCall(FLInlinedCall InlinedCall);

  /// Append an entry without uniquing it, so that an existing table can be
  /// copied or loaded without changing its indexes.
  void appendScope(FLScope Scope);
  void appendSrcLoc(const FLSrcLoc &SrcLoc);
  void appendInlinedCall(const FLInlinedCall &InlinedCall);
  /// Recompute the uniquing indexes from the tables.
  void rebuildUniquingIndexes();

  ResolvedFLSrcLoc getResolvedSrcLoc(FLIndex<uint32_t> SrcLocIdx, FLIndex<uint16_t> InlinedAtIdx = FLIndex<uint16_t>()) {
    if (InlinedAtIdx)
      return InlinedCalls[InlinedAtIdx.get()].getInlinee()->getResolvedSrcLoc(SrcLocIdx);
    FLSrcLoc SrcLoc = SrcLocs[SrcLocIdx.get()];
    DILocalScope *Scope = Scopes[SrcLoc.ScopeIdx.get()].get();
    return ResolvedFLSrcLoc { SrcLoc.Line, SrcLoc.Column, Scope };
  }
  ResolvedFLInlinedCall getResolvedInlinedCall(FLIndex<uint16_t> InlinedAtIdx) {
    FLInlinedCall InlinedCall = InlinedCalls[InlinedAtIdx.get()];
    std::unique_ptr<ResolvedFLInlinedCall> InlinedAt;
    if (InlinedCall.InlinedAtIdx)
      InlinedAt.reset(new ResolvedFLInlinedCall(getResolvedInlinedCall(InlinedCall.InlinedAtIdx)));
    ResolvedFLSrcLoc SrcLoc = getResolvedSrcLoc(InlinedCall.SrcLocIdx, InlinedCall.InlinedAtIdx);
    return ResolvedFLInlinedCall {
      SrcLoc, InlinedAtIdx.get(), InlinedCall.MaxAtomGroup,
      InlinedCall.Uniquable, std::move(InlinedAt) };
  }

  static bool classof(const Metadata *MD) {
    return MD->getMetadataID() == DIFunctionLocalMetadataKind;
  }
};

/// Builder class used to perform the initial population for FLMD, and
/// optionally future updates.
/// 
/// Besides allowing direct modification of arrays that normally have a limited
/// interface, this also ensures that some of the elements that are required to
/// appear at a fixed position in the array  
class FLMDBuilder {
  DIFunctionLocalMetadata *FLContext;
  DenseMap<FLScope, FLIndex<uint16_t>> ScopeMap;
  DenseMap<FLSrcLoc, FLIndex<uint32_t>> SrcLocMap;
  DenseMap<FLInlinedCall, uint16_t> UniqueInlinedCalls;
public:

  // TODO: Should we accept DILocalScope here? Doing so unfortunately forces the
  // slow path of using the non-inlined FLScope constructor.
  FLIndex<uint16_t> getScope(MDNode* Scope) {
    FLScope InsertedScope(Scope);
    if (auto ScopeIt = ScopeMap.find(InsertedScope); ScopeIt != ScopeMap.end())
      return ScopeIt->second;
    FLContext->appendScope(InsertedScope);
    uint16_t Index = FLContext->Scopes.size() - 1;
    ScopeMap.insert({InsertedScope, Index});
    return Index;
  }
  FLIndex<uint32_t> getSrcLoc(uint32_t Line, uint16_t Column, MDNode* Scope) {
    // TODO: This might be slightly faster if we store the Scope in the
    // SrcLocMap, so we don't have to do two map lookups. The map would pack
    // less well, though.
    FLIndex<uint16_t> ScopeIdx = getScope(Scope);
    FLSrcLoc InsertedSrcLoc(Line, Column, ScopeIdx);
    if (auto SrcLocIt = SrcLocMap.find(InsertedSrcLoc); SrcLocIt != SrcLocMap.end())
      return SrcLocIt->second;
    FLContext->appendSrcLoc(InsertedSrcLoc);
    uint32_t Index = FLContext->SrcLocs.size() - 1;
    SrcLocMap.insert({InsertedSrcLoc, Index});
    return Index;
  }

  FLMDBuilder(DIFunctionLocalMetadata *FLContext, const DISubprogram *SP);
};

} // end namespace llvm


#endif // LLVM_IR_FUNCTIONLOCALMETADATA_H
