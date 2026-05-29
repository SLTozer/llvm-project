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
#include <optional>

using namespace llvm;

#if LLVM_ENABLE_DEBUGLOC_TRACKING_ORIGIN
#include "llvm/Support/Signals.h"

DbgLocOrigin::DbgLocOrigin(bool ShouldCollectTrace) {
  if (!ShouldCollectTrace)
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

#if LLVM_ENABLE_DEBUGLOC_TRACKING_COVERAGE
DILocAndCoverageTracking::DILocAndCoverageTracking(const DILocation *L)
    : TrackingMDNodeRef(const_cast<DILocation *>(L)), DbgLocOrigin(!L),
      Kind(DebugLocKind::Normal) {}
#endif // LLVM_ENABLE_DEBUGLOC_TRACKING_COVERAGE


// Methods used for transitioning to Function-Local Metadata
DebugLoc::DebugLoc(const DILocation *L, std::nullopt_t)
  : Loc(const_cast<DILocation *>(L)) {}
DebugLoc DebugLoc::get(LLVMContext &Context, unsigned Line, unsigned Column,
                       Metadata *Scope, DebugLoc InlinedAt,
                       bool ImplicitCode, uint64_t AtomGroup, uint8_t AtomRank) {
  // Forward to DILocation::get
  return DebugLoc(DILocation::get(Context, Line, Column, Scope, InlinedAt.getAsMDNode(), ImplicitCode, AtomGroup, AtomRank), std::nullopt);
}
DebugLoc DebugLoc::getDistinct(LLVMContext &Context, unsigned Line,
                               unsigned Column, Metadata *Scope,
                               DebugLoc InlinedAt, bool ImplicitCode,
                               uint64_t AtomGroup, uint8_t AtomRank) {
  // Forward to DILocation::getDistinct
  return DebugLoc(DILocation::getDistinct(Context, Line, Column, Scope, InlinedAt.getAsMDNode(), ImplicitCode, AtomGroup, AtomRank), std::nullopt);
}

DebugLoc DebugLoc::getFromValidDILocationLoopMDOperand(const MDOperand &MDO) {
  if (auto *DIL = dyn_cast<DILocation>(MDO))
    return DebugLoc(DIL, std::nullopt);
  return DebugLoc();
}
//===----------------------------------------------------------------------===//
// DebugLoc Implementation
//===----------------------------------------------------------------------===//

unsigned DebugLoc::getLine() const {
  assert(privateGet() && "Expected valid DebugLoc");
  return privateGet()->getLine();
}

unsigned DebugLoc::getCol() const {
  assert(privateGet() && "Expected valid DebugLoc");
  return privateGet()->getColumn();
}

DILocalScope *DebugLoc::getScope() const {
  assert(privateGet() && "Expected valid DebugLoc");
  return privateGet()->getScope();
}

DebugLoc DebugLoc::getInlinedAt() const {
  assert(privateGet() && "Expected valid DebugLoc");
  return DebugLoc(privateGet()->getInlinedAt(), std::nullopt);
}

DILocalScope *DebugLoc::getInlinedAtScope() const {
  return cast<DILocation>(Loc)->getInlinedAtScope();
}

DebugLoc DebugLoc::getFnDebugLoc() const {
  // FIXME: Add a method on \a DILocation that does this work.
  const MDNode *Scope = getInlinedAtScope();
  if (auto *SP = getDISubprogram(Scope))
    return DebugLoc(DILocation::get(SP->getContext(), SP->getScopeLine(), 0, SP), std::nullopt);

  return DebugLoc();
}

MDNode *DebugLoc::getAsMDNode() const { return Loc; }

bool DebugLoc::isImplicitCode() const {
  if (DILocation *Loc = privateGet())
    return Loc->isImplicitCode();
  return true;
}

void DebugLoc::setImplicitCode(bool ImplicitCode) {
  if (DILocation *Loc = privateGet())
    Loc->setImplicitCode(ImplicitCode);
}

DebugLoc DebugLoc::replaceInlinedAtSubprogram(
    const DebugLoc &RootLoc, DISubprogram &NewSP, LLVMContext &Ctx,
    DenseMap<const MDNode *, MDNode *> &Cache) {
  return DebugLoc(
    replaceInlinedAtSubprogram(RootLoc.privateGet(), NewSP, Ctx, Cache),
    std::nullopt);
}
DILocation *DebugLoc::replaceInlinedAtSubprogram(
    const DILocation *RootLoc, DISubprogram &NewSP, LLVMContext &Ctx,
    DenseMap<const MDNode *, MDNode *> &Cache) {
  SmallVector<DILocation *> LocChain;
  DILocation *CachedResult = nullptr;

  // Collect the inline chain, stopping if we find a location that has already
  // been processed.
  for (const DILocation *Loc = RootLoc; Loc; Loc = Loc->getInlinedAt()) {
    if (auto It = Cache.find(Loc); It != Cache.end()) {
      CachedResult = cast<DILocation>(It->second);
      break;
    }
    LocChain.push_back(const_cast<DILocation*>(Loc));
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
    if (auto *Found = Cache[IA.privateGet()]) {
      Last = DebugLoc(Found);
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
    Cache[MD.privateGet()] = Last.privateGet();
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
  if (!LocA || !LocB) {
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
  return DebugLoc(DILocation::getMergedLocation(LocA.privateGet(), LocB.privateGet()), std::nullopt);
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

void DebugLoc::print(raw_ostream &OS, const Module *M, bool IsForDebug) const {
  return privateGet()->print(OS, M, IsForDebug);
}
void DebugLoc::print(raw_ostream &OS, ModuleSlotTracker &MST, const Module *M,
                     bool IsForDebug) const {
  return privateGet()->print(OS, MST, M, IsForDebug);
}
void DebugLoc::printAsOperand(raw_ostream &OS, const Module *M) const {
  return privateGet()->printAsOperand(OS, M);
}
void DebugLoc::printAsOperand(raw_ostream &OS, ModuleSlotTracker &MST,
                     const Module *M) const {
  return privateGet()->printAsOperand(OS, MST, M);
}
bool DebugLoc::isDistinct() const {
  return privateGet()->isDistinct();
}

uint64_t DebugLoc::getAtomGroup() const {
  return privateGet()->getAtomGroup();
}
uint8_t DebugLoc::getAtomRank() const {
  return privateGet()->getAtomRank();
}

DebugLoc DebugLoc::getWithoutAtom() const {
  return DebugLoc(privateGet()->getWithoutAtom(), std::nullopt);
}

StringRef DebugLoc::getSubprogramLinkageName() const {
  return privateGet()->getSubprogramLinkageName();
}

DIFile *DebugLoc::getFile() const {
  return privateGet()->getFile();
}
StringRef DebugLoc::getFilename() const {
  return privateGet()->getFilename();
}
StringRef DebugLoc::getDirectory() const {
  return privateGet()->getDirectory();
}
std::optional<StringRef> DebugLoc::getSource() const {
  return privateGet()->getSource();
}

DebugLoc DebugLoc::getInlinedAtLocation() const {
  return DebugLoc(privateGet()->getInlinedAtLocation(), std::nullopt);
}

unsigned DebugLoc::getDiscriminator() const {
  return privateGet()->getDiscriminator();
}

bool DebugLoc::isPseudoProbeDiscriminator(unsigned Discriminator) {
  return DILocation::isPseudoProbeDiscriminator(Discriminator);
}

/// Returns a new DebugLoc with updated \p Discriminator.
DebugLoc DebugLoc::cloneWithDiscriminator(unsigned Discriminator) const {
  return DebugLoc(privateGet()->cloneWithDiscriminator(Discriminator), std::nullopt);
}

/// Returns a new DebugLoc with updated base discriminator \p BD. Only the
/// base discriminator is set in the new DebugLoc, the other encoded values
/// are elided.
/// If the discriminator cannot be encoded, the function returns std::nullopt.
std::optional<DebugLoc>
DebugLoc::cloneWithBaseDiscriminator(unsigned BD) const {
  std::optional<const DILocation*> DL = privateGet()->cloneWithBaseDiscriminator(BD);
  if (DL)
    return DebugLoc(*DL, std::nullopt);
  return std::nullopt;
}

/// Returns the duplication factor stored in the discriminator, or 1 if no
/// duplication factor (or 0) is encoded.
unsigned DebugLoc::getDuplicationFactor() const {
  return privateGet()->getDuplicationFactor();
}

/// Returns the copy identifier stored in the discriminator.
unsigned DebugLoc::getCopyIdentifier() const {
  return privateGet()->getCopyIdentifier();
}

/// Returns the base discriminator stored in the discriminator.
unsigned DebugLoc::getBaseDiscriminator() const {
  return privateGet()->getBaseDiscriminator();
}

/// Returns a new DebugLoc with duplication factor \p DF * current
/// duplication factor encoded in the discriminator. The current duplication
/// factor is as defined by getDuplicationFactor().
/// Returns std::nullopt if encoding failed.
std::optional<DebugLoc>
DebugLoc::cloneByMultiplyingDuplicationFactor(unsigned DF) const {
  std::optional<const DILocation*> DL = privateGet()->cloneByMultiplyingDuplicationFactor(DF);
  if (DL)
    return DebugLoc(*DL, std::nullopt);
  return std::nullopt;
}

LLVM_ABI std::optional<unsigned>
DebugLoc::encodeDiscriminator(unsigned BD, unsigned DF, unsigned CI) {
  return DILocation::encodeDiscriminator(BD, DF, CI);
}

Metadata *DebugLoc::getRawScope() const {
  return privateGet()->getRawScope();
}
Metadata *DebugLoc::getRawInlinedAt() const {
  return privateGet()->getRawInlinedAt();
}

