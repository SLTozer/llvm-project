//===-- DebugLoc.cpp - Implement DebugLoc class ---------------------------===//
//
// Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
//
//===----------------------------------------------------------------------===//

#include "llvm/IR/DebugLoc.h"
#include "llvm/Config/llvm-config.h"
#include "llvm/IR/DebugInfo.h"
#include "llvm/IR/DebugInfoMetadata.h"
#include "llvm/IR/Function.h"
#include "llvm/IR/FunctionLocalMetadata.h"
#include <cstdint>
#include <optional>

using namespace llvm;

namespace llvm {
extern LLVM_ABI cl::opt<bool> PickMergedSourceLocations;
} // namespace llvm

#if LLVM_ENABLE_DEBUGLOC_TRACKING_ORIGIN
#include "llvm/Support/Signals.h"
namespace llvm {
bool DebugLocOriginCollectionEnabled = false;
} // namespace llvm

DbgLocOrigin::DbgLocOrigin(bool ShouldCollectTrace) {
  if (!ShouldCollectTrace || !DebugLocOriginCollectionEnabled)
    return;
  auto &[Depth, StackTrace] = StackTraces.emplace_back();
  Depth = sys::getStackTrace(StackTrace);
}
void DbgLocOrigin::addTrace() {
  // We only want to add new stacktraces if we already have one: addTrace exists
  // to provide more context to how missing DebugLocs have propagated through
  // the program, but by design if there is no existing stacktrace then we have
  // decided not to track this DebugLoc as being "missing".
  if (StackTraces.empty())
    return;
  auto &[Depth, StackTrace] = StackTraces.emplace_back();
  Depth = sys::getStackTrace(StackTrace);
}
#endif // LLVM_ENABLE_DEBUGLOC_TRACKING_ORIGIN

#if LLVM_USE_FLMD_SOURCE_LOCS
/// Stores the context needed to convert between MD and FLMD source locations.
struct FLMDSourceLocConversionContext {
  DenseMap<DILocation *, FLIndex<uint16_t>> InlinedCallLocMap;
  DenseMap<std::pair<FLIndex<uint16_t>, DIFunctionLocalMetadata*>, DILocation *> InlinedCallIdxToDILocMap;
  DenseMap<FLIndex<uint16_t>, uint16_t> MaxAtomMap;
};

static FLMDSourceLocConversionContext FLMDConversionContext;

FLIndex<uint16_t> getInlinedDILocationToFLIndex(DILocation *DIL) {
  // No inlinedAt -> empty inlinedAt index.
  if (!DIL)
    return FLIndex<uint16_t>();
  assert(DIL->isDistinct());
  if (auto ExistingIdxIt = FLMDConversionContext.InlinedCallLocMap.find(DIL);
      ExistingIdxIt != FLMDConversionContext.InlinedCallLocMap.end())
    return ExistingIdxIt->second;
  // Get inlinedAtIdx...
  FLIndex<uint16_t> InlinedAtIdx = getInlinedDILocationToFLIndex(DIL);
  // Get srcLocIdx...
  DILocalScope *OrigScope = DIL->getScope();
  DIFunctionLocalMetadata *OrigFLMD = Function::getFunctionForSP(OrigScope->getSubprogram())->FLMD;
  FLIndex<uint32_t> SrcLocIdx = OrigFLMD->getFLSrcLocIdx(DIL->getLine(), DIL->getColumn(), OrigScope);
  DIFunctionLocalMetadata *InlinedAtFLMD = Function::getFunctionForSP(DIL->getInlinedAtScope()->getSubprogram())->FLMD;
  FLIndex<uint16_t> NewIdx = InlinedAtFLMD->addInlinedCall(FLInlinedCall(SrcLocIdx, InlinedAtIdx, OrigFLMD));
  FLMDConversionContext.InlinedCallLocMap.insert({DIL, NewIdx});
  FLMDConversionContext.InlinedCallIdxToDILocMap.insert({{NewIdx, InlinedAtFLMD}, DIL});
  return NewIdx;
}

FLDebugLoc FLDebugLoc::getFromDILocation(const DILocation *DIL) {
  FLIndex<uint16_t> InlinedAtIdx = getInlinedDILocationToFLIndex(DIL->getInlinedAt());
  DILocalScope *OrigScope = DIL->getScope();
  DIFunctionLocalMetadata *OrigFLMD = Function::getFunctionForSP(OrigScope->getSubprogram())->FLMD;
  FLIndex<uint32_t> SrcLocIdx = OrigFLMD->getFLSrcLocIdx(DIL->getLine(), DIL->getColumn(), OrigScope);
  return FLDebugLoc(SrcLocIdx, InlinedAtIdx, DIL->getAtomGroup(), DIL->getAtomRank());
}

DebugLoc DebugLoc::getFromDILocation(const DILocation *DIL) {
  FLDebugLoc Storage = FLDebugLoc::getFromDILocation(DIL);
  DIFunctionLocalMetadata *FLContext = Function::getFunctionForSP(DIL->getInlinedAtScope()->getSubprogram())->FLMD;
  return DebugLoc(Storage, FLContext);
}

DILocation *DebugLoc::convertToDILocation() const {
  if (!*this)
    return nullptr;
  if (SelfInlinedCallIdx) {
    if (auto ExistingDILIt = FLMDConversionContext.InlinedCallIdxToDILocMap.find({SelfInlinedCallIdx, FLContext}); ExistingDILIt != FLMDConversionContext.InlinedCallIdxToDILocMap.end())
      return ExistingDILIt->second;
  }
  DILocation *InlinedAt = getInlinedAt().convertToDILocation();
  SrcLocData SrcLoc = getSrcLocData();
  DILocation *Result = DILocation::get(FLContext->getContext(), SrcLoc.Line, SrcLoc.Column, SrcLoc.Scope, InlinedAt, false, Storage.AtomGroup, Storage.AtomRank);
  if (SelfInlinedCallIdx) {
    FLMDConversionContext.InlinedCallLocMap.insert({Result, SelfInlinedCallIdx});
    FLMDConversionContext.InlinedCallIdxToDILocMap.insert({{SelfInlinedCallIdx, FLContext}, Result});
  }
  return Result;
}
#endif

//===----------------------------------------------------------------------===//
// DebugLoc Implementation
//===----------------------------------------------------------------------===//

#if LLVM_USE_FLMD_SOURCE_LOCS
DebugLoc DebugLoc::get(
    LLVMContext &Context, unsigned Line, unsigned Column, Metadata *Scope,
    DebugLoc InlinedAt, bool ImplicitCode, uint64_t AtomGroup,
    uint8_t AtomRank) {
  DISubprogram *SP = cast<DILocalScope>(Scope)->getSubprogram();
  OrigFLMD = Function::getFunctionForSP(SP)->FLMD;

  return DebugLoc::getFromDILocation(DILocation::get(Context, Line, Column, Scope, InlinedAt.getAsDILocation(), ImplicitCode, AtomGroup, AtomRank));
}
DebugLoc DebugLoc::getDistinct(
    LLVMContext &Context, unsigned Line, unsigned Column, Metadata *Scope,
    DebugLoc InlinedAt, bool ImplicitCode, uint64_t AtomGroup,
    uint8_t AtomRank) {
  return DebugLoc::getFromDILocation(DILocation::getDistinct(Context, Line, Column, Scope, InlinedAt.getAsDILocation(), ImplicitCode, AtomGroup, AtomRank));
}
#else
DebugLoc DebugLoc::get(
    LLVMContext &Context, unsigned Line, unsigned Column, Metadata *Scope,
    DebugLoc InlinedAt, bool ImplicitCode, uint64_t AtomGroup,
    uint8_t AtomRank) {
  return DebugLoc::getFromDILocation(DILocation::get(Context, Line, Column, Scope, InlinedAt.getAsDILocation(), ImplicitCode, AtomGroup, AtomRank));
}
DebugLoc DebugLoc::getDistinct(
    LLVMContext &Context, unsigned Line, unsigned Column, Metadata *Scope,
    DebugLoc InlinedAt, bool ImplicitCode, uint64_t AtomGroup,
    uint8_t AtomRank) {
  return DebugLoc::getFromDILocation(DILocation::getDistinct(Context, Line, Column, Scope, InlinedAt.getAsDILocation(), ImplicitCode, AtomGroup, AtomRank));
}
#endif

DebugLoc DebugLoc::getFromMDNode(const MDNode *MD) {
  return DebugLoc::getFromDILocation(dyn_cast_or_null<DILocation>(MD));
}

#if LLVM_USE_FLMD_SOURCE_LOCS
unsigned DebugLoc::getLine() const {
  assert(Storage && "Expected valid DebugLoc");
  return FLContext->getSrcLoc(Storage.SrcLocIdx).Line;
}

unsigned DebugLoc::getCol() const {
  assert(Storage && "Expected valid DebugLoc");
  return FLContext->getSrcLoc(Storage.SrcLocIdx).Column;
}

DILocalScope *DebugLoc::getScope() const {
  assert(Storage && "Expected valid DebugLoc");
  return FLContext->getScope(FLContext->getSrcLoc(Storage.SrcLocIdx).ScopeIdx);
}

DebugLoc DebugLoc::getInlinedAt() const {
  assert(Storage && "Expected valid DebugLoc");
  return DebugLoc(FLDebugLoc::getInlinedCallLoc(Storage.InlinedAtIdx), FLContext);
}
DILocalScope *DebugLoc::getInlinedAtScope() const {
  FLDebugLoc RootLoc = Storage;
  while (Storage.InlinedAtIdx) {
    RootLoc = FLDebugLoc::getInlinedCallLoc(FLContext->getInlinedCall(Storage.InlinedAtIdx));
  }
  return FLContext->getScope(FLContext->getSrcLoc(RootLoc.SrcLocIdx).ScopeIdx);
}

DebugLoc DebugLoc::getFnDebugLoc() const {
  constexpr uint16_t SubprogramScopeIndex = 0;
  DISubprogram *InlinedAtSP = cast<DISubprogram>(FLContext->Scopes[SubprogramScopeIndex].Scope);
  FLDebugLoc NewFLDebugLoc(
    FLContext->getFLSrcLocIdx(
      InlinedAtSP->getScopeLine(), 0, SubprogramScopeIndex),
    FLIndex<uint16_t>());
  return DebugLoc(NewFLDebugLoc, FLContext);
}

MDNode *DebugLoc::getAsMDNode() const {
  return convertToDILocation();
}

bool DebugLoc::isImplicitCode() const {
  /// FIXME: We could add implicitcode to the FLSrcLoc, but do we actually need to?
  return false;
}

void DebugLoc::setImplicitCode(bool ImplicitCode) {
}

DebugLoc DebugLoc::replaceInlinedAtSubprogram(
    const DebugLoc &RootLoc, DISubprogram &NewSP, LLVMContext &Ctx,
    DenseMap<const MDNode *, MDNode *> &Cache) {
  return getFromDILocation(
    replaceInlinedAtSubprogram(RootLoc.convertToDILocation(), NewSP, Ctx, Cache));
}
DILocation *DebugLoc::replaceInlinedAtSubprogram(
    const DILocation *RootLoc, DISubprogram &NewSP, LLVMContext &Ctx,
    DenseMap<const MDNode *, MDNode *> &Cache) {
  SmallVector<DILocation *> LocChain;
  DILocation *CachedResult = nullptr;

  // Collect the inline chain, stopping if we find a location that has already
  // been processed.
  for (const DILocation *Storage = RootLoc; Storage; Storage = Storage->getInlinedAt()) {
    if (auto It = Cache.find(Storage); It != Cache.end()) {
      CachedResult = cast<DILocation>(It->second);
      break;
    }
    LocChain.push_back(const_cast<DILocation*>(Storage));
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
  for (DILocation *LocToUpdate : reverse(LocChain)) {
    UpdatedLoc =
        DILocation::get(Ctx, LocToUpdate->getLine(), LocToUpdate->getColumn(),
                        LocToUpdate->getScope(), UpdatedLoc);
    Cache[LocToUpdate] = UpdatedLoc;
  }

  return UpdatedLoc;
}


DebugLoc DebugLoc::appendInlinedAt(const DebugLoc &DL, DebugLoc InlinedAt,
                                   LLVMContext &Ctx,
                                   DenseMap<const MDNode *, MDNode *> &Cache) {
  SmallVector<DebugLoc, 3> InlinedAtLocations;
  DebugLoc Last = InlinedAt;
  DebugLoc CurInlinedAt = DL;

  // Gather all the inlined-at nodes.
  while (DebugLoc IA = CurInlinedAt->getInlinedAt()) {
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
  // Key Instructions: InlinedAt fields don't need atom info.
  for (DebugLoc MD : reverse(InlinedAtLocations)) {
    Last = DebugLoc::getDistinct(
        Ctx, MD->getLine(), MD->getColumn(), MD->getScope(), Last);
    Cache[MD] = Last;
  }

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
  if (!(PickMergedSourceLocations && (LocA || LocB)) && (!LocA || !LocB)) {
    // If coverage tracking is enabled, prioritize returning empty non-annotated
    // locations to empty annotated locations.
#if LLVM_ENABLE_DEBUGLOC_TRACKING_COVERAGE
    if (!LocA && LocA.getKind() == DebugLocKind::Normal)
      return LocA;
    if (!LocB && LocB.getKind() == DebugLocKind::Normal)
      return LocB;
#endif // LLVM_ENABLE_DEBUGLOC_TRACKING_COVERAGE
    if (!LocA)
      return LocA;
    return LocB;
  }
  return DILocation::getMergedLocation(LocA, LocB);
}

#if !defined(NDEBUG) || defined(LLVM_ENABLE_DUMP)
LLVM_DUMP_METHOD void DebugLoc::dump() const { print(dbgs()); }
#endif

void DebugLoc::print(raw_ostream &OS) const {
  if (!Storage)
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

void DebugLoc::print(raw_ostream &OS, const Module *M, bool IsForDebug) const {
  return get()->print(OS, M, IsForDebug);
}
void DebugLoc::print(raw_ostream &OS, ModuleSlotTracker &MST, const Module *M,
                     bool IsForDebug) const {
  return get()->print(OS, MST, M, IsForDebug);
}
void DebugLoc::printAsOperand(raw_ostream &OS, const Module *M) const {
  return get()->printAsOperand(OS, M);
}
void DebugLoc::printAsOperand(raw_ostream &OS, ModuleSlotTracker &MST,
                     const Module *M) const {
  return get()->printAsOperand(OS, MST, M);
}
bool DebugLoc::isDistinct() const {
  return get()->isDistinct();
}

LLVMContext &DebugLoc::getContext() const { return FLContext->getContext(); }

uint64_t DebugLoc::getAtomGroup() const {
  return get()->getAtomGroup();
}
uint8_t DebugLoc::getAtomRank() const {
  return get()->getAtomRank();
}

DebugLoc DebugLoc::getWithoutAtom() const {
  return get()->getWithoutAtom();
}

StringRef DebugLoc::getSubprogramLinkageName() const {
  return get()->getSubprogramLinkageName();
}

DIFile *DebugLoc::getFile() const {
  return get()->getFile();
}
StringRef DebugLoc::getFilename() const {
  return get()->getFilename();
}
StringRef DebugLoc::getDirectory() const {
  return get()->getDirectory();
}
std::optional<StringRef> DebugLoc::getSource() const {
  return get()->getSource();
}

DebugLoc DebugLoc::getInlinedAtLocation() const {
  return get()->getInlinedAtLocation();
}

unsigned DebugLoc::getDiscriminator() const {
  return get()->getDiscriminator();
}

/// Returns a new DebugLoc with updated \p Discriminator.
DebugLoc DebugLoc::cloneWithDiscriminator(unsigned Discriminator) const {
  return get()->cloneWithDiscriminator(Discriminator);
}

/// Returns a new DebugLoc with updated base discriminator \p BD. Only the
/// base discriminator is set in the new DebugLoc, the other encoded values
/// are elided.
/// If the discriminator cannot be encoded, the function returns std::nullopt.
std::optional<DebugLoc>
DebugLoc::cloneWithBaseDiscriminator(unsigned BD) const {
  std::optional<const DILocation*> DL = get()->cloneWithBaseDiscriminator(BD);
  if (DL)
    return *DL;
  return std::nullopt;
}

/// Returns the duplication factor stored in the discriminator, or 1 if no
/// duplication factor (or 0) is encoded.
unsigned DebugLoc::getDuplicationFactor() const {
  return get()->getDuplicationFactor();
}

/// Returns the copy identifier stored in the discriminator.
unsigned DebugLoc::getCopyIdentifier() const {
  return get()->getCopyIdentifier();
}

/// Returns the base discriminator stored in the discriminator.
unsigned DebugLoc::getBaseDiscriminator() const {
  return get()->getBaseDiscriminator();
}

/// Returns a new DebugLoc with duplication factor \p DF * current
/// duplication factor encoded in the discriminator. The current duplication
/// factor is as defined by getDuplicationFactor().
/// Returns std::nullopt if encoding failed.
std::optional<DebugLoc>
DebugLoc::cloneByMultiplyingDuplicationFactor(unsigned DF) const {
  std::optional<const DILocation*> DL = get()->cloneByMultiplyingDuplicationFactor(DF);
  if (DL)
    return *DL;
  return std::nullopt;
}

Metadata *DebugLoc::getRawScope() const {
  assert(Storage && "Expected valid DebugLoc");
  FLIndex<uint32_t> SrcLocIdx = Storage.get().isInlinedCall()
    ? FLContext->getInlinedCall(Storage.get().InlinedAtIdx).SrcLocIdx :
    : Storage.get().SrcLocIdx;
  FLSrcLoc SrcLoc = FLContext->getSrcLoc();
  return FLContext->get()->getRawScope();
}
Metadata *DebugLoc::getRawInlinedAt() const {
  return get()->getRawInlinedAt();
}

bool DebugLoc::isPseudoProbeDiscriminator(unsigned Discriminator) {
  return DILocation::isPseudoProbeDiscriminator(Discriminator);
}

LLVM_ABI std::optional<unsigned>
DebugLoc::encodeDiscriminator(unsigned BD, unsigned DF, unsigned CI) {
  return DILocation::encodeDiscriminator(BD, DF, CI);
}
#else
unsigned DebugLoc::getLine() const {
  assert(Storage && "Expected valid DebugLoc");
  return Storage.get()->getLine();
}

unsigned DebugLoc::getCol() const {
  assert(Storage && "Expected valid DebugLoc");
  return Storage.get()->getColumn();
}

DILocalScope *DebugLoc::getScope() const {
  assert(Storage && "Expected valid DebugLoc");
  return Storage.get()->getScope();
}

DebugLoc DebugLoc::getInlinedAt() const {
  assert(Storage && "Expected valid DebugLoc");
  return DebugLoc::getFromDILocation(Storage.get()->getInlinedAt());
}

DILocalScope *DebugLoc::getInlinedAtScope() const {
  return cast<DILocation>(Storage.get())->getInlinedAtScope();
}

DebugLoc DebugLoc::getFnDebugLoc() const {
  // FIXME: Add a method on \a DILocation that does this work.
  const MDNode *Scope = getInlinedAtScope();
  if (auto *SP = getDISubprogram(Scope))
    return DebugLoc::get(SP->getContext(), SP->getScopeLine(), 0, SP);

  return DebugLoc();
}

MDNode *DebugLoc::getAsMDNode() const { return Storage.get(); }

bool DebugLoc::isImplicitCode() const {
  if (Storage)
    return Storage.get()->isImplicitCode();
  return true;
}

void DebugLoc::setImplicitCode(bool ImplicitCode) {
  if (Storage)
    Storage.get()->setImplicitCode(ImplicitCode);
}

DebugLoc DebugLoc::replaceInlinedAtSubprogram(
    const DebugLoc &RootLocDL, DISubprogram &NewSP, LLVMContext &Ctx,
    DenseMap<const MDNode *, MDNode *> &Cache) {
  DILocation *RootLoc = RootLocDL.getAsDILocation();
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

  return DebugLoc::getFromDILocation(UpdatedLoc);
}

DebugLoc DebugLoc::appendInlinedAt(const DebugLoc &DL, DILocation *InlinedAt,
                                   LLVMContext &Ctx,
                                   DenseMap<const MDNode *, MDNode *> &Cache) {
  SmallVector<DILocation *, 3> InlinedAtLocations;
  DILocation *Last = InlinedAt;
  DILocation *CurInlinedAt = DL.Storage.get();

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
  // Key Instructions: InlinedAt fields don't need atom info.
  for (const DILocation *MD : reverse(InlinedAtLocations))
    Cache[MD] = Last = DILocation::getDistinct(
        Ctx, MD->getLine(), MD->getColumn(), MD->getScope(), Last);

  return DebugLoc::getFromDILocation(Last);
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
  if (!LocA || !LocB) {
    // If we are missing either location but have requested
    // PickMergedSourceLocations, then just forward straight to the
    // DILocation version.
    if (PickMergedSourceLocations)
      return DebugLoc::getFromDILocation(DILocation::getMergedLocation(LocA.getAsDILocation(), LocB.getAsDILocation()));
    // If coverage tracking is enabled, prioritize returning empty non-annotated
    // locations to empty annotated locations.
#if LLVM_ENABLE_DEBUGLOC_TRACKING_COVERAGE
    if (!LocA && LocA.getKind() == DebugLocKind::Normal)
      return LocA;
    if (!LocB && LocB.getKind() == DebugLocKind::Normal)
      return LocB;
#endif // LLVM_ENABLE_DEBUGLOC_TRACKING_COVERAGE
    if (!LocA)
      return LocA;
    return LocB;
  }
  return DebugLoc::getFromDILocation(DILocation::getMergedLocation(LocA.getAsDILocation(), LocB.getAsDILocation()));
}

#if !defined(NDEBUG) || defined(LLVM_ENABLE_DUMP)
LLVM_DUMP_METHOD void DebugLoc::dump() const { print(dbgs()); }
LLVM_DUMP_METHOD void DebugLoc::dump(const Module *M) const { print(dbgs(), M); }
#endif

void DebugLoc::print(raw_ostream &OS) const {
  if (!Storage)
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

void DebugLoc::print(raw_ostream &OS, const Module *M, bool IsForDebug) const {
  return Storage.get()->print(OS, M, IsForDebug);
}
void DebugLoc::print(raw_ostream &OS, ModuleSlotTracker &MST, const Module *M,
                     bool IsForDebug) const {
  return Storage.get()->print(OS, MST, M, IsForDebug);
}
void DebugLoc::printAsOperand(raw_ostream &OS, const Module *M) const {
  return Storage.get()->printAsOperand(OS, M);
}
void DebugLoc::printAsOperand(raw_ostream &OS, ModuleSlotTracker &MST,
                     const Module *M) const {
  return Storage.get()->printAsOperand(OS, MST, M);
}
bool DebugLoc::isDistinct() const {
  return Storage.get()->isDistinct();
}

LLVMContext &DebugLoc::getContext() const { return Storage.get()->getContext(); }

uint64_t DebugLoc::getAtomGroup() const {
  return Storage.get()->getAtomGroup();
}
uint8_t DebugLoc::getAtomRank() const {
  return Storage.get()->getAtomRank();
}

DebugLoc DebugLoc::getWithoutAtom() const {
  return DebugLoc::getFromDILocation(Storage.get()->getWithoutAtom());
}

StringRef DebugLoc::getSubprogramLinkageName() const {
  return Storage.get()->getSubprogramLinkageName();
}

DIFile *DebugLoc::getFile() const {
  return Storage.get()->getFile();
}
StringRef DebugLoc::getFilename() const {
  return Storage.get()->getFilename();
}
StringRef DebugLoc::getDirectory() const {
  return Storage.get()->getDirectory();
}
std::optional<StringRef> DebugLoc::getSource() const {
  return Storage.get()->getSource();
}

DebugLoc DebugLoc::getInlinedAtLocation() const {
  return DebugLoc::getFromDILocation(Storage.get()->getInlinedAtLocation());
}

unsigned DebugLoc::getDiscriminator() const {
  return Storage.get()->getDiscriminator();
}

/// Returns a new DebugLoc with updated \p Discriminator.
DebugLoc DebugLoc::cloneWithDiscriminator(unsigned Discriminator) const {
  return DebugLoc::getFromDILocation(Storage.get()->cloneWithDiscriminator(Discriminator));
}

/// Returns a new DebugLoc with updated base discriminator \p BD. Only the
/// base discriminator is set in the new DebugLoc, the other encoded values
/// are elided.
/// If the discriminator cannot be encoded, the function returns std::nullopt.
std::optional<DebugLoc>
DebugLoc::cloneWithBaseDiscriminator(unsigned BD) const {
  std::optional<const DILocation*> DL = Storage.get()->cloneWithBaseDiscriminator(BD);
  if (DL)
    return DebugLoc::getFromDILocation(*DL);
  return std::nullopt;
}

/// Returns the duplication factor stored in the discriminator, or 1 if no
/// duplication factor (or 0) is encoded.
unsigned DebugLoc::getDuplicationFactor() const {
  return Storage.get()->getDuplicationFactor();
}

/// Returns the copy identifier stored in the discriminator.
unsigned DebugLoc::getCopyIdentifier() const {
  return Storage.get()->getCopyIdentifier();
}

/// Returns the base discriminator stored in the discriminator.
unsigned DebugLoc::getBaseDiscriminator() const {
  return Storage.get()->getBaseDiscriminator();
}

/// Returns a new DebugLoc with duplication factor \p DF * current
/// duplication factor encoded in the discriminator. The current duplication
/// factor is as defined by getDuplicationFactor().
/// Returns std::nullopt if encoding failed.
std::optional<DebugLoc>
DebugLoc::cloneByMultiplyingDuplicationFactor(unsigned DF) const {
  std::optional<const DILocation*> DL = Storage.get()->cloneByMultiplyingDuplicationFactor(DF);
  if (DL)
    return DebugLoc::getFromDILocation(*DL);
  return std::nullopt;
}

Metadata *DebugLoc::getRawScope() const {
  return Storage.get()->getRawScope();
}
Metadata *DebugLoc::getRawInlinedAt() const {
  return Storage.get()->getRawInlinedAt();
}

bool DebugLoc::isPseudoProbeDiscriminator(unsigned Discriminator) {
  return DILocation::isPseudoProbeDiscriminator(Discriminator);
}

LLVM_ABI std::optional<unsigned>
DebugLoc::encodeDiscriminator(unsigned BD, unsigned DF, unsigned CI) {
  return DILocation::encodeDiscriminator(BD, DF, CI);
}
#endif