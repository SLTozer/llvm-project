//===- Function.cpp - Implement the Global object classes -----------------===//
//
// Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
//
//===----------------------------------------------------------------------===//
//
// This file implements function-local metadata types.
//
//===----------------------------------------------------------------------===//

#include "llvm/IR/FunctionLocalMetadata.h"
#include "llvm/IR/DebugInfoMetadata.h"

using namespace llvm;


FLInlinedCall FLInlinedCall::fromRawParts(uint64_t RawInt, DIFunctionLocalMetadata *Inlinee) {
  FLInlinedCall Result;
  Result.SrcLocIdx = FLIndex<uint32_t>::fromRaw(RawInt >> 32);
  Result.InlinedAtIdx = FLIndex<uint16_t>::fromRaw(RawInt >> 16);
  Result.MaxAtomGroup = (RawInt & 0xfffe) >> 1;
  Result.Uniquable = (RawInt & 1);
  Result.InlineeFLMD = Inlinee;
  return Result;
}

FLIndex<uint16_t> DIFunctionLocalMetadata::getFLScopeIdx(DILocalScope *Scope) {
  auto [It, Inserted] = ScopeIndex.try_emplace(Scope, Scopes.size());
  if (!Inserted)
    return It->second;
  if (Scopes.size() > 0)
    assert(Scope->getSubprogram() == Scopes[0]);
  Scopes.push_back(FLScope(Scope));
  return Scopes.size() - 1;
}

// Returns the index of the entry equivalent to \p Entry, or Table.size() after
// adding the new entry to \p Index; the caller appends it.
template <typename EntryT>
static std::pair<uint32_t, bool> internEntry(FLEntryIndex<EntryT> &Index,
                                             ArrayRef<EntryT> Table,
                                             const EntryT &Entry) {
  unsigned Hash = Entry.getHash();
  uint32_t NewIdx = Table.size();
  auto [It, Inserted] = Index.insert_as(
      (uint64_t)Hash << 32 | NewIdx,
      typename FLEntryIndexInfo<EntryT>::Key{Entry, Table, Hash});
  return {Inserted ? NewIdx : uint32_t(*It), Inserted};
}

FLIndex<uint32_t>
DIFunctionLocalMetadata::getFLSrcLocIdx(const FLSrcLoc &SrcLoc) {
  auto [Idx, Inserted] = internEntry<FLSrcLoc>(SrcLocIndex, SrcLocs, SrcLoc);
  if (Inserted)
    SrcLocs.push_back(SrcLoc);
  return Idx;
}

FLIndex<uint16_t>
DIFunctionLocalMetadata::addInlinedCall(FLInlinedCall InlinedCall) {
  if (InlinedCall.Uniquable) {
    auto [Idx, Inserted] = internEntry<FLInlinedCall>(
        UniquedInlinedCallIndex, InlinedCalls, InlinedCall);
    if (!Inserted) {
      FLInlinedCall &Existing = InlinedCalls[Idx];
      Existing.MaxAtomGroup =
          std::max(InlinedCall.MaxAtomGroup, Existing.MaxAtomGroup);
      return FLIndex<uint16_t>(Idx);
    }
  }
  InlinedCalls.push_back(InlinedCall);
  return InlinedCalls.size() - 1;
}

void DIFunctionLocalMetadata::appendScope(FLScope Scope) {
  ScopeIndex.try_emplace(Scope.Scope, Scopes.size());
  Scopes.push_back(Scope);
}

void DIFunctionLocalMetadata::appendSrcLoc(const FLSrcLoc &SrcLoc) {
  internEntry<FLSrcLoc>(SrcLocIndex, SrcLocs, SrcLoc);
  SrcLocs.push_back(SrcLoc);
}

void DIFunctionLocalMetadata::appendInlinedCall(
    const FLInlinedCall &InlinedCall) {
  if (InlinedCall.Uniquable)
    internEntry<FLInlinedCall>(UniquedInlinedCallIndex, InlinedCalls,
                               InlinedCall);
  InlinedCalls.push_back(InlinedCall);
}

void DIFunctionLocalMetadata::rebuildUniquingIndexes() {
  ScopeIndex.clear();
  SrcLocIndex.clear();
  UniquedInlinedCallIndex.clear();
  ScopeIndex.reserve(Scopes.size());
  SrcLocIndex.reserve(SrcLocs.size());
  for (auto [Idx, Scope] : enumerate(Scopes))
    ScopeIndex.try_emplace(Scope.Scope, Idx);
  ArrayRef<FLSrcLoc> SrcLocTable(SrcLocs);
  for (auto [Idx, SrcLoc] : enumerate(SrcLocs))
    internEntry<FLSrcLoc>(SrcLocIndex, SrcLocTable.take_front(Idx), SrcLoc);
  ArrayRef<FLInlinedCall> InlinedCallTable(InlinedCalls);
  for (auto [Idx, InlinedCall] : enumerate(InlinedCalls))
    if (InlinedCall.Uniquable)
      internEntry<FLInlinedCall>(UniquedInlinedCallIndex,
                                 InlinedCallTable.take_front(Idx), InlinedCall);
}


FLMDBuilder::FLMDBuilder(DIFunctionLocalMetadata *FLContext, const DISubprogram *SP) : FLContext(FLContext) {
  /// If FLContext is already populated, load its contents into the builder map.
  if (!FLContext->Scopes.empty() || !FLContext->SrcLocs.empty()) {
    assert(FLContext->Scopes[0].Scope == SP &&
      "FLContext already contains non-matching subprogram?");
    assert(FLContext->SrcLocs[0] == FLSrcLoc(0, 0, 0) &&
      "FLContext already contains non-matching srcLocs?");
    assert(FLContext->SrcLocs[1] == FLSrcLoc(SP->getLine(), 0, 0) &&
      "FLContext already contains non-matching srcLocs?");
    assert(FLContext->SrcLocs[2] == FLSrcLoc(SP->getScopeLine(), 0, 0) &&
      "FLContext already contains non-matching srcLocs?");
    for (auto [Idx, SrcLoc] : enumerate(FLContext->SrcLocs))
      SrcLocMap.insert({SrcLoc, Idx});
    for (auto [Idx, Scope] : enumerate(FLContext->Scopes))
      ScopeMap.insert({Scope, Idx});
    for (auto [Idx, InlinedCall] : enumerate(FLContext->InlinedCalls))
      if (InlinedCall.Uniquable)
        UniqueInlinedCalls.insert({InlinedCall, Idx});
    return;
  }
  assert(FLContext->Scopes.empty() && FLContext->SrcLocs.empty()
    && "Creating a builder for an already-exinst FLContext currently unsupported.");
  FLContext->appendScope(FLScope{ const_cast<DISubprogram*>(SP) });
  ScopeMap.insert({FLScope{ const_cast<DISubprogram*>(SP) }, 0});
  FLContext->appendSrcLoc(FLSrcLoc(0, 0, 0));
  FLContext->appendSrcLoc(FLSrcLoc(SP->getLine(), 0, 0));
  FLContext->appendSrcLoc(FLSrcLoc(SP->getScopeLine(), 0, 0));
  SrcLocMap.insert({FLSrcLoc(0, 0, 0), 0});
  SrcLocMap.insert({FLSrcLoc(SP->getLine(), 0, 0), 1});
  SrcLocMap.insert({FLSrcLoc(SP->getScopeLine(), 0, 0), 2});
}
