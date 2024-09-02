//===-- DebugLoc.cpp - Implement DebugLoc class ---------------------------===//
//
// Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
//
//===----------------------------------------------------------------------===//

#include "llvm/ADT/Hashing.h"
#include "llvm/IR/DebugLoc.h"
#include "llvm/Config/llvm-config.h"
#include "llvm/IR/DebugInfo.h"
#include "llvm/IR/Function.h"

#ifdef LLVM_ENABLE_DEBUGLOC_COVERAGE_TRACKING
#include "llvm/Support/Signals.h"

using namespace llvm;

struct StacktraceOrList {
  union {
    std::array<void *, DbgLocOriginStacktrace::MaxDepth> Single;
    std::array<size_t, DbgLocOriginStacktrace::MaxDepth> STList;
  };
  uint8_t Size : 7;
  uint8_t IsList : 1;
  StacktraceOrList(int Size, std::array<size_t, DbgLocOriginStacktrace::MaxDepth> STList) : STList(STList), Size(Size), IsList(0) {}
  StacktraceOrList(int Size, std::array<void *, DbgLocOriginStacktrace::MaxDepth> Single) : Single(Single), Size(Size), IsList(1) {}
  StacktraceOrList(bool Tombstone = false) : Size(Tombstone ? 0x7F : 0), IsList(Tombstone ? 1 : 0) {
    static_assert(DbgLocOriginStacktrace::MaxDepth < 0x7F, "Size of backtrace array must fit in 7 bits - 1");
  }
};

hash_code hash_value(const StacktraceOrList &S) {
  static_assert(DbgLocOriginStacktrace::MaxDepth < (1 << 7));
  hash_code Result;
  if (S.IsList) {
    Result = hash_combine_range(S.Single.begin(), S.Single.begin() + S.Size);
  } else {
    Result = hash_combine_range(S.STList.begin(), S.STList.begin() + S.Size);
  }
  return Result;
}

template <> struct DenseMapInfo<StacktraceOrList> {
  static inline StacktraceOrList getEmptyKey() {
    return StacktraceOrList();
  }

  static inline StacktraceOrList getTombstoneKey() {
    return StacktraceOrList(true);
  }

  static unsigned getHashValue(const StacktraceOrList &Val) {
    return hash_value(Val);
  }

  static bool isEqual(const StacktraceOrList &LHS, const StacktraceOrList &RHS) {
    if (LHS.IsList != RHS.IsList)
      return false;
    if (LHS.IsList)
      return ArrayRef(LHS.Single.begin(), LHS.Single.begin() + LHS.Size) == ArrayRef(RHS.Single.begin(), RHS.Single.begin() + RHS.Size);
    return ArrayRef(LHS.STList.begin(), LHS.STList.begin() + LHS.Size) == ArrayRef(RHS.STList.begin(), RHS.STList.begin() + RHS.Size);
  }
};

// Storage for every unique stacktrace or list of stacktraces collected across this run of the program.
static std::vector<StacktraceOrList> CollectedStacktraces(1, StacktraceOrList());
// Mapping from a unique stacktrace or list of stacktraces to an index in the CollectedStacktraces vector.
static DenseMap<StacktraceOrList, size_t> StacktraceStorageMap;

size_t getIndex(const StacktraceOrList &S) {
  // Special empty value that can't be inserted into the map.
  if (S.Size == 0)
    return 0;
  auto [It, R] = StacktraceStorageMap.insert({S, CollectedStacktraces.size()});
  if (R)
    CollectedStacktraces.push_back(S);
  return It->second;
}
inline StacktraceOrList getStacktraceFromIndex(size_t Idx) {
  return CollectedStacktraces[Idx];
}
// Given an index to an existing stored stacktrace, and a new 
size_t getIndexForAddedTrace(size_t Idx, StacktraceOrList S) {
  size_t AddedIdx = getIndex(S);
  if (Idx == 0)
    return AddedIdx;
  StacktraceOrList Current = getStacktraceFromIndex(Idx);
  StacktraceOrList New;
  if (Current.IsList) {
    std::array<size_t, DbgLocOriginStacktrace::MaxDepth> STList = {Idx, AddedIdx};
    New = StacktraceOrList(2, STList);
  } else {
    // There is no way to represent a STList-backtrace containing more than MaxDepth
    // backtraces, so just leave it unappended.
    // FIXME: We could rotate it, so that we get the MaxDepth-most recent
    // backtraces rather than the oldest?
    if (Current.Size == DbgLocOriginStacktrace::MaxDepth)
      return Idx;
    New = StacktraceOrList(Current.Size + 1, Current.STList);
    New.STList[Current.Size] = AddedIdx;
  }
  return getIndex(S);
}


DILocAndCoverageTracking::DILocAndCoverageTracking(const DILocation *L)
    : TrackingMDNodeRef(const_cast<DILocation *>(L)),
      Kind(DebugLocKind::Normal), Origin(!L) {}

DbgLocOriginStacktrace::DbgLocOriginStacktrace(bool ShouldCollectTrace) : StacktraceIdx(0) {
  if (!ShouldCollectTrace)
    return;
  std::array<void *, DbgLocOriginStacktrace::MaxDepth> Stacktrace;
  int Depth = sys::getStackTrace(Stacktrace);
  StacktraceIdx = getIndexForAddedTrace(StacktraceIdx, StacktraceOrList(Depth, Stacktrace));
}
void DbgLocOriginStacktrace::addTrace() {
  if (StacktraceIdx == 0)
    return;
  std::array<void *, DbgLocOriginStacktrace::MaxDepth> Stacktrace;
  int Depth = sys::getStackTrace(Stacktrace);
  StacktraceIdx = getIndex(StacktraceOrList(Depth, Stacktrace));
}
SmallVector<std::pair<int, std::array<void *, DbgLocOriginStacktrace::MaxDepth>>, 0> DbgLocOriginStacktrace::getStacktraces() {
  SmallVector<std::pair<int, std::array<void *, DbgLocOriginStacktrace::MaxDepth>>, 0> Stacktraces;
  if (StacktraceIdx == 0)
    return Stacktraces;
  StacktraceOrList S = getStacktraceFromIndex(StacktraceIdx);
  if (S.IsList) {
    Stacktraces.push_back({(int)S.Size, S.Single});
  } else {
    for (size_t SingleIdx : ArrayRef(S.STList.data(), S.Size)) {
      StacktraceOrList SingleS = getStacktraceFromIndex(SingleIdx);
      Stacktraces.push_back({(int)SingleS.Size, SingleS.Single});
    }
  }
  return Stacktraces;
}

DebugLoc DebugLoc::getTemporary() {
  return DebugLoc(DebugLocKind::Temporary);
}
DebugLoc DebugLoc::getUnknown() {
  return DebugLoc(DebugLocKind::Unknown);
}
DebugLoc DebugLoc::getLineZero() {
  return DebugLoc(DebugLocKind::LineZero);
}

#else

using namespace llvm;

DebugLoc DebugLoc::getTemporary() { return DebugLoc(); }
DebugLoc DebugLoc::getUnknown() { return DebugLoc(); }
DebugLoc DebugLoc::getLineZero() { return DebugLoc(); }
#endif // LLVM_ENABLE_DEBUGLOC_COVERAGE_TRACKING

//===----------------------------------------------------------------------===//
// DebugLoc Implementation
//===----------------------------------------------------------------------===//
DebugLoc::DebugLoc(const DILocation *L) : Loc(const_cast<DILocation *>(L)) {}
DebugLoc::DebugLoc(const MDNode *L) : Loc(const_cast<MDNode *>(L)) {}

DILocation *DebugLoc::get() const {
  return cast_or_null<DILocation>(Loc.get());
}

unsigned DebugLoc::getLine() const {
  assert(get() && "Expected valid DebugLoc");
  return get()->getLine();
}

unsigned DebugLoc::getCol() const {
  assert(get() && "Expected valid DebugLoc");
  return get()->getColumn();
}

MDNode *DebugLoc::getScope() const {
  assert(get() && "Expected valid DebugLoc");
  return get()->getScope();
}

DILocation *DebugLoc::getInlinedAt() const {
  assert(get() && "Expected valid DebugLoc");
  return get()->getInlinedAt();
}

MDNode *DebugLoc::getInlinedAtScope() const {
  return cast<DILocation>(Loc)->getInlinedAtScope();
}

DebugLoc DebugLoc::getFnDebugLoc() const {
  // FIXME: Add a method on \a DILocation that does this work.
  const MDNode *Scope = getInlinedAtScope();
  if (auto *SP = getDISubprogram(Scope))
    return DILocation::get(SP->getContext(), SP->getScopeLine(), 0, SP);

  return DebugLoc();
}

bool DebugLoc::isImplicitCode() const {
  if (DILocation *Loc = get()) {
    return Loc->isImplicitCode();
  }
  return true;
}

void DebugLoc::setImplicitCode(bool ImplicitCode) {
  if (DILocation *Loc = get()) {
    Loc->setImplicitCode(ImplicitCode);
  }
}

DebugLoc DebugLoc::replaceInlinedAtSubprogram(
    const DebugLoc &RootLoc, DISubprogram &NewSP, LLVMContext &Ctx,
    DenseMap<const MDNode *, MDNode *> &Cache) {
  SmallVector<DILocation *> LocChain;
  DILocation *CachedResult = nullptr;

  // Collect the inline chain, stopping if we find a location that has already
  // been processed.
  for (DILocation *Loc = RootLoc; Loc; Loc = Loc->getInlinedAt()) {
    if (auto It = Cache.find(Loc); It != Cache.end()) {
      CachedResult = cast<DILocation>(It->second);
      break;
    }
    LocChain.push_back(Loc);
  }

  DILocation *UpdatedLoc = CachedResult;
  if (!UpdatedLoc) {
    // If no cache hits, then back() is the end of the inline chain, that is,
    // the DILocation whose scope ends in the Subprogram to be replaced.
    DILocation *LocToUpdate = LocChain.pop_back_val();
    DIScope *NewScope = DILocalScope::cloneScopeForSubprogram(
        *LocToUpdate->getScope(), NewSP, Ctx, Cache);
    UpdatedLoc = DILocation::get(Ctx, LocToUpdate->getLine(),
                                 LocToUpdate->getColumn(), NewScope);
    Cache[LocToUpdate] = UpdatedLoc;
  }

  // Recreate the location chain, bottom-up, starting at the new scope (or a
  // cached result).
  for (const DILocation *LocToUpdate : reverse(LocChain)) {
    UpdatedLoc =
        DILocation::get(Ctx, LocToUpdate->getLine(), LocToUpdate->getColumn(),
                        LocToUpdate->getScope(), UpdatedLoc);
    Cache[LocToUpdate] = UpdatedLoc;
  }

  return UpdatedLoc;
}

DebugLoc DebugLoc::appendInlinedAt(const DebugLoc &DL, DILocation *InlinedAt,
                                   LLVMContext &Ctx,
                                   DenseMap<const MDNode *, MDNode *> &Cache) {
  SmallVector<DILocation *, 3> InlinedAtLocations;
  DILocation *Last = InlinedAt;
  DILocation *CurInlinedAt = DL;

  // Gather all the inlined-at nodes.
  while (DILocation *IA = CurInlinedAt->getInlinedAt()) {
    // Skip any we've already built nodes for.
    if (auto *Found = Cache[IA]) {
      Last = cast<DILocation>(Found);
      break;
    }

    InlinedAtLocations.push_back(IA);
    CurInlinedAt = IA;
  }

  // Starting from the top, rebuild the nodes to point to the new inlined-at
  // location (then rebuilding the rest of the chain behind it) and update the
  // map of already-constructed inlined-at nodes.
  for (const DILocation *MD : reverse(InlinedAtLocations))
    Cache[MD] = Last = DILocation::getDistinct(
        Ctx, MD->getLine(), MD->getColumn(), MD->getScope(), Last);

  return Last;
}

DebugLoc DebugLoc::getMergedLocations(ArrayRef<DebugLoc> Locs) {
  if (Locs.empty())
    return DebugLoc();
  if (Locs.size() == 1)
    return Locs[0];
  DebugLoc Merged = Locs[0];
  for (const DebugLoc &DL : llvm::drop_begin(Locs)) {
    Merged = getMergedLocation(Merged, DL);
    if (!Merged)
      break;
  }
  return Merged;
}
DebugLoc DebugLoc::getMergedLocation(DebugLoc LocA, DebugLoc LocB) {
  if (!LocA)
    return LocA.getCopied();
  if (!LocB)
    return LocB.getCopied();
  return DILocation::getMergedLocation(LocA, LocB);
}

#if !defined(NDEBUG) || defined(LLVM_ENABLE_DUMP)
LLVM_DUMP_METHOD void DebugLoc::dump() const { print(dbgs()); }
#endif

void DebugLoc::print(raw_ostream &OS) const {
  if (!Loc)
    return;

  // Print source line info.
  auto *Scope = cast<DIScope>(getScope());
  OS << Scope->getFilename();
  OS << ':' << getLine();
  if (getCol() != 0)
    OS << ':' << getCol();

  if (DebugLoc InlinedAtDL = getInlinedAt()) {
    OS << " @[ ";
    InlinedAtDL.print(OS);
    OS << " ]";
  }
}
