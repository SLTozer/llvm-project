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
#include "llvm/Support/Casting.h"

using namespace llvm;

namespace llvm {
extern LLVM_ABI cl::opt<bool> PickMergedSourceLocations;
} // namespace llvm

// NOLINTBEGIN(llvm-debug-loc-*)

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

//===----------------------------------------------------------------------===//
// DebugLoc Implementation
//===----------------------------------------------------------------------===//

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

DebugLoc DebugLoc::getFromMDNode(const MDNode *MD) {
  return DebugLoc::getFromDILocation(dyn_cast_or_null<DILocation>(MD));
}

unsigned DebugLoc::getLine() const {
  assert(Loc && "Expected valid DebugLoc");
  return Loc->getLine();
}

unsigned DebugLoc::getCol() const {
  assert(Loc && "Expected valid DebugLoc");
  return Loc->getColumn();
}

DILocalScope *DebugLoc::getScope() const {
  assert(Loc && "Expected valid DebugLoc");
  return Loc->getScope();
}

DebugLoc DebugLoc::getInlinedAt() const {
  assert(Loc && "Expected valid DebugLoc");
  return DebugLoc::getFromDILocation(Loc->getInlinedAt());
}

DILocalScope *DebugLoc::getInlinedAtScope() const {
  return cast<DILocation>(Loc)->getInlinedAtScope();
}

DebugLoc DebugLoc::getFnDebugLoc() const {
  // FIXME: Add a method on \a DILocation that does this work.
  const MDNode *Scope = getInlinedAtScope();
  if (auto *SP = getDISubprogram(Scope))
    return DebugLoc::get(SP->getContext(), SP->getScopeLine(), 0, SP);

  return DebugLoc();
}

MDNode *DebugLoc::getAsMDNode() const { return Loc; }

bool DebugLoc::isImplicitCode() const {
  if (Loc)
    return Loc->isImplicitCode();
  return true;
}

void DebugLoc::setImplicitCode(bool ImplicitCode) {
  if (Loc)
    Loc->setImplicitCode(ImplicitCode);
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
  DILocation *CurInlinedAt = DL.Loc;

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
  return Loc->print(OS, M, IsForDebug);
}
void DebugLoc::print(raw_ostream &OS, ModuleSlotTracker &MST, const Module *M,
                     bool IsForDebug) const {
  return Loc->print(OS, MST, M, IsForDebug);
}
void DebugLoc::printAsOperand(raw_ostream &OS, const Module *M) const {
  return Loc->printAsOperand(OS, M);
}
void DebugLoc::printAsOperand(raw_ostream &OS, ModuleSlotTracker &MST,
                     const Module *M) const {
  return Loc->printAsOperand(OS, MST, M);
}
bool DebugLoc::isDistinct() const {
  return Loc->isDistinct();
}

LLVMContext &DebugLoc::getContext() const { return Loc->getContext(); }

uint64_t DebugLoc::getAtomGroup() const {
  return Loc->getAtomGroup();
}
uint8_t DebugLoc::getAtomRank() const {
  return Loc->getAtomRank();
}

DebugLoc DebugLoc::getWithoutAtom() const {
  return DebugLoc::getFromDILocation(Loc->getWithoutAtom());
}

StringRef DebugLoc::getSubprogramLinkageName() const {
  return Loc->getSubprogramLinkageName();
}

DIFile *DebugLoc::getFile() const {
  return Loc->getFile();
}
StringRef DebugLoc::getFilename() const {
  return Loc->getFilename();
}
StringRef DebugLoc::getDirectory() const {
  return Loc->getDirectory();
}
std::optional<StringRef> DebugLoc::getSource() const {
  return Loc->getSource();
}

DebugLoc DebugLoc::getInlinedAtLocation() const {
  return DebugLoc::getFromDILocation(Loc->getInlinedAtLocation());
}

unsigned DebugLoc::getDiscriminator() const {
  return Loc->getDiscriminator();
}

/// Returns a new DebugLoc with updated \p Discriminator.
DebugLoc DebugLoc::cloneWithDiscriminator(unsigned Discriminator) const {
  return DebugLoc::getFromDILocation(Loc->cloneWithDiscriminator(Discriminator));
}

/// Returns a new DebugLoc with updated base discriminator \p BD. Only the
/// base discriminator is set in the new DebugLoc, the other encoded values
/// are elided.
/// If the discriminator cannot be encoded, the function returns std::nullopt.
std::optional<DebugLoc>
DebugLoc::cloneWithBaseDiscriminator(unsigned BD) const {
  std::optional<const DILocation*> DL = Loc->cloneWithBaseDiscriminator(BD);
  if (DL)
    return DebugLoc::getFromDILocation(*DL);
  return std::nullopt;
}

/// Returns the duplication factor stored in the discriminator, or 1 if no
/// duplication factor (or 0) is encoded.
unsigned DebugLoc::getDuplicationFactor() const {
  return Loc->getDuplicationFactor();
}

/// Returns the copy identifier stored in the discriminator.
unsigned DebugLoc::getCopyIdentifier() const {
  return Loc->getCopyIdentifier();
}

/// Returns the base discriminator stored in the discriminator.
unsigned DebugLoc::getBaseDiscriminator() const {
  return Loc->getBaseDiscriminator();
}

/// Returns a new DebugLoc with duplication factor \p DF * current
/// duplication factor encoded in the discriminator. The current duplication
/// factor is as defined by getDuplicationFactor().
/// Returns std::nullopt if encoding failed.
std::optional<DebugLoc>
DebugLoc::cloneByMultiplyingDuplicationFactor(unsigned DF) const {
  std::optional<const DILocation*> DL = Loc->cloneByMultiplyingDuplicationFactor(DF);
  if (DL)
    return DebugLoc::getFromDILocation(*DL);
  return std::nullopt;
}

Metadata *DebugLoc::getRawScope() const {
  return Loc->getRawScope();
}
Metadata *DebugLoc::getRawInlinedAt() const {
  return Loc->getRawInlinedAt();
}

bool DebugLoc::isPseudoProbeDiscriminator(unsigned Discriminator) {
  return DILocation::isPseudoProbeDiscriminator(Discriminator);
}

LLVM_ABI std::optional<unsigned>
DebugLoc::encodeDiscriminator(unsigned BD, unsigned DF, unsigned CI) {
  return DILocation::encodeDiscriminator(BD, DF, CI);
}

// NOLINTEND(llvm-debug-loc-*)
