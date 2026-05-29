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

#ifndef LLVM_IR_DEBUGLOC_H
#define LLVM_IR_DEBUGLOC_H

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

extern cl::opt<bool> EnableFSDiscriminator;

class LLVMContext;
class raw_ostream;
class DILocation;
class Function;

#if LLVM_ENABLE_DEBUGLOC_TRACKING_COVERAGE
#if LLVM_ENABLE_DEBUGLOC_TRACKING_ORIGIN
struct DbgLocOrigin {
  static constexpr unsigned long MaxDepth = 16;
  using StackTracesTy =
      SmallVector<std::pair<int, std::array<void *, MaxDepth>>, 0>;
  StackTracesTy StackTraces;
  DbgLocOrigin(bool ShouldCollectTrace);
  void addTrace();
  const StackTracesTy &getOriginStackTraces() const { return StackTraces; };
};
#else
struct DbgLocOrigin {
  DbgLocOrigin(bool) {}
};
#endif
// Used to represent different "kinds" of DebugLoc, expressing that the
// instruction it is part of is either normal and should contain a valid
// DILocation, or otherwise describing the reason why the instruction does
// not contain a valid DILocation.
enum class DebugLocKind : uint8_t {
  // The instruction is expected to contain a valid DILocation.
  Normal,
  // The instruction is compiler-generated, i.e. it is not associated with any
  // line in the original source.
  CompilerGenerated,
  // The instruction has intentionally had its source location removed,
  // typically because it was moved outside of its original control-flow and
  // presenting the prior source location would be misleading for debuggers
  // or profilers.
  Dropped,
  // The instruction does not have a known or currently knowable source
  // location, e.g. the attribution is ambiguous in a way that can't be
  // represented, or determining the correct location is complicated and
  // requires future developer effort.
  Unknown,
  // DebugLoc is attached to an instruction that we don't expect to be
  // emitted, and so can omit a valid DILocation; we don't expect to ever try
  // and emit these into the line table, and trying to do so is a sign that
  // something has gone wrong (most likely a DebugLoc leaking from a transient
  // compiler-generated instruction).
  Temporary
};

// Extends a DILocation pointer to also store a DebugLocKind and Origin,
// allowing Debugify to ignore intentionally-empty DebugLocs and display the
// code responsible for generating unintentionally-empty DebugLocs.
// Currently we only need to track the Origin of this DILoc when using a
// DebugLoc that is not annotated (i.e. has DebugLocKind::Normal) and has a
// null DILocation, so only collect the origin stacktrace in those cases.
class DILocAndCoverageTracking : public DbgLocOrigin {
  DILocation *Loc;

public:
  DebugLocKind Kind;
  // Default constructor for empty DebugLocs.
  DILocAndCoverageTracking()
      : DbgLocOrigin(true), Loc(nullptr), Kind(DebugLocKind::Normal) {}
  // Valid or nullptr DILocation*, no annotative DebugLocKind.
  DILocAndCoverageTracking(const DILocation *Loc)
      : DbgLocOrigin(!Loc), Loc(const_cast<DILocation *>(Loc)),
        Kind(DebugLocKind::Normal) {}
  // Explicit DebugLocKind, which always means a nullptr DILocation*.
  DILocAndCoverageTracking(DebugLocKind Kind)
      : DbgLocOrigin(Kind == DebugLocKind::Normal), Loc(nullptr), Kind(Kind) {}

  operator DILocation *() const { return Loc; }
};
template <> struct simplify_type<DILocAndCoverageTracking> {
  using SimpleType = DILocation *;

  static DILocation *getSimplifiedValue(DILocAndCoverageTracking &MD) {
    return MD;
  }
};
template <> struct simplify_type<const DILocAndCoverageTracking> {
  using SimpleType = DILocation *;

  static DILocation *getSimplifiedValue(const DILocAndCoverageTracking &MD) {
    return MD;
  }
};

using DebugLocRef = DILocAndCoverageTracking;
#else
using DebugLocRef = DILocation *;
#endif // LLVM_ENABLE_DEBUGLOC_TRACKING_COVERAGE

/// A debug info location.
///
/// This class is a wrapper around an \a DILocation
/// pointer.
///
/// To avoid extra includes, \a DebugLoc doubles the \a DILocation API with a
/// one based on relatively opaque \a MDNode pointers.
class DebugLoc {
  friend struct DenseMapInfo<const DILocation *>;
  friend struct DebugLocKey;
  friend class DILocation;
  friend class DebugVariable;
  friend class SlotTracker;
  friend class ValueEnumerator;

  friend hash_code hash_value(const DebugLoc &Val);

  DebugLocRef Loc;

  LLVM_ABI DebugLoc(const DILocation *L, std::nullopt_t);
  DILocation *privateGet() const { return Loc; };

public:
  DebugLoc() = default;
  LLVM_DEPRECATED("Avoid using direct pointers to construct DebugLoc", "DebugLoc()")
  DebugLoc(std::nullptr_t) : Loc() {}
  LLVM_DEPRECATED("Avoid pointer comparisons for DebugLoc", "DebugLoc::operator bool()")
  bool operator==(std::nullptr_t) const { return Loc; }
  LLVM_DEPRECATED("Avoid using direct DILocation pointers", "")
  bool operator==(const DILocation *Other) const {
    return privateGet() == Other;
  };

  /// Construct from an \a DILocation.
  LLVM_DEPRECATED("Avoid using direct DILocation references", "DebugLoc::get[Distinct]")
  LLVM_ABI DebugLoc(const DILocation *L) : Loc(const_cast<DILocation *>(L)) {}

  static DebugLoc getFromValidDILocationLoopMDOperand(const MDOperand &MDO);

  static DebugLoc get(LLVMContext &Context, unsigned Line, unsigned Column,
                      Metadata *Scope, DebugLoc InlinedAt = DebugLoc(),
                      bool ImplicitCode = false, uint64_t AtomGroup = 0, uint8_t AtomRank = 0);
  static DebugLoc getDistinct(LLVMContext &Context, unsigned Line,
                              unsigned Column, Metadata *Scope,
                              DebugLoc InlinedAt = DebugLoc(), bool ImplicitCode = false,
                              uint64_t AtomGroup = 0, uint8_t AtomRank = 0);

#if LLVM_ENABLE_DEBUGLOC_TRACKING_COVERAGE
  DebugLoc(DebugLocKind Kind) : Loc(Kind) {}
  DebugLocKind getKind() const { return Loc.Kind; }
#endif

#if LLVM_ENABLE_DEBUGLOC_TRACKING_COVERAGE
  static inline DebugLoc getTemporary() {
    return DebugLoc(DebugLocKind::Temporary);
  }
  static inline DebugLoc getUnknown() {
    return DebugLoc(DebugLocKind::Unknown);
  }
  static inline DebugLoc getCompilerGenerated() {
    return DebugLoc(DebugLocKind::CompilerGenerated);
  }
  static inline DebugLoc getDropped() {
    return DebugLoc(DebugLocKind::Dropped);
  }
#else
  static inline DebugLoc getTemporary() { return DebugLoc(); }
  static inline DebugLoc getUnknown() { return DebugLoc(); }
  static inline DebugLoc getCompilerGenerated() { return DebugLoc(); }
  static inline DebugLoc getDropped() { return DebugLoc(); }
#endif // LLVM_ENABLE_DEBUGLOC_TRACKING_COVERAGE

  /// When two instructions are combined into a single instruction we also
  /// need to combine the original locations into a single location.
  /// When the locations are the same we can use either location.
  /// When they differ, we need a third location which is distinct from
  /// either. If they share a common scope, use this scope and compare the
  /// line/column pair of the locations with the common scope:
  /// * if both match, keep the line and column;
  /// * if only the line number matches, keep the line and set the column as
  /// 0;
  /// * otherwise set line and column as 0.
  /// If they do not share a common scope the location is ambiguous and can't
  /// be represented in a line entry. In this case, set line and column as 0
  /// and use the scope of any location.
  ///
  /// \p LocA \p LocB: The locations to be merged.
  LLVM_ABI static DebugLoc getMergedLocation(DebugLoc LocA, DebugLoc LocB);

  /// Try to combine the vector of locations passed as input in a single one.
  /// This function applies getMergedLocation() repeatedly left-to-right.
  ///
  /// \p Locs: The locations to be merged.
  LLVM_ABI static DebugLoc getMergedLocations(ArrayRef<DebugLoc> Locs);

  /// If this DebugLoc is non-empty, returns this DebugLoc; otherwise, selects
  /// \p Other.
  /// In coverage-tracking builds, this also accounts for whether this or
  /// \p Other have an annotative DebugLocKind applied, such that if both are
  /// empty but exactly one has an annotation, we prefer that annotated
  /// location.
  DebugLoc orElse(DebugLoc Other) const {
    if (*this)
      return *this;
#if LLVM_ENABLE_DEBUGLOC_TRACKING_COVERAGE
    if (Other)
      return Other;
    if (getKind() != DebugLocKind::Normal)
      return *this;
    if (Other.getKind() != DebugLocKind::Normal)
      return Other;
    return *this;
#else
    return Other;
#endif // LLVM_ENABLE_DEBUGLOC_TRACKING_COVERAGE
  }

#if LLVM_ENABLE_DEBUGLOC_TRACKING_ORIGIN
  const DbgLocOrigin::StackTracesTy &getOriginStackTraces() const {
    return Loc.getOriginStackTraces();
  }
  DebugLoc getCopied() const {
    DebugLoc NewDL = *this;
    NewDL.Loc.addTrace();
    return NewDL;
  }
#else
  DebugLoc getCopied() const { return *this; }
#endif

  /// Get the underlying \a DILocation.
  ///
  /// \pre !*this or \c isa<DILocation>(getAsMDNode()).
  /// @{
  LLVM_DEPRECATED("Avoid using direct DILocation references, replace with pure DebugLoc methods", "")
  DILocation *get() const { return Loc; }
  LLVM_DEPRECATED("Avoid using direct DILocation references, replace with pure DebugLoc methods", "")
  operator DILocation *() const { return get(); }
  // FIXME: All methods on DebugLoc should work for DILocation as well, but we
  // may allow a CMake flag to toggle DILocation access back again temporarily
  // for downstream users.
#if true
  const DebugLoc *operator->() const { return const_cast<DebugLoc*>(this); }
  const DebugLoc &operator*() const { return *const_cast<DebugLoc*>(this); }
  DebugLoc *operator->() { return this; }
  DebugLoc &operator*() { return *this; }
#else
  #warning "Dependence on DILocation* is deprecated; please enable the "\
           "DebugLoc-only interface as soon as possible."
  DILocation *operator->() const { return get(); }
  DILocation &operator*() const { return *get(); }
#endif
  /// @}

  /// Check for null.
  ///
  /// Check for null in a way that is safe with broken debug info.  Unlike
  /// the conversion to \c DILocation, this doesn't require that \c Loc is of
  /// the right type.  Important for cases like \a llvm::StripDebugInfo() and
  /// \a Instruction::hasMetadata().
  explicit operator bool() const { return Loc; }

  enum { ReplaceLastInlinedAt = true };
  /// Rebuild the entire inlined-at chain for this instruction so that the top
  /// of the chain now is inlined-at the new call site.
  /// \param   InlinedAt The new outermost inlined-at in the chain.
  LLVM_ABI static DebugLoc
  appendInlinedAt(const DebugLoc &DL, DebugLoc InlinedAt, LLVMContext &Ctx,
                  DenseMap<const MDNode *, MDNode *> &Cache);

  /// Return true if the source locations match, ignoring isImplicitCode and
  /// source atom info.
  bool isSameSourceLocation(const DebugLoc &Other) const {
    if (privateGet() == Other.privateGet())
      return true;
    return ((bool)*this == (bool)Other) && getLine() == Other.getLine() &&
           getCol() == Other.getCol() && getScope() == Other.getScope() &&
           getInlinedAt() == Other.getInlinedAt();
  }

  LLVM_ABI unsigned getLine() const;
  LLVM_ABI unsigned getCol() const;
  LLVM_ABI unsigned getColumn() const { return getCol(); }
  LLVM_ABI DILocalScope *getScope() const;
  LLVM_ABI DebugLoc getInlinedAt() const;
  
  LLVMContext &getContext() const { return Loc->getContext(); }

  /// Get the fully inlined-at scope for a DebugLoc.
  ///
  /// Gets the inlined-at scope for a DebugLoc.
  LLVM_ABI DILocalScope *getInlinedAtScope() const;

  /// Rebuild the entire inline-at chain by replacing the subprogram at the
  /// end of the chain with NewSP.
  LLVM_ABI static DebugLoc
  replaceInlinedAtSubprogram(const DebugLoc &DL, DISubprogram &NewSP,
                             LLVMContext &Ctx,
                             DenseMap<const MDNode *, MDNode *> &Cache);
  LLVM_ABI static DILocation *
  replaceInlinedAtSubprogram(const DILocation *DL, DISubprogram &NewSP,
                             LLVMContext &Ctx,
                             DenseMap<const MDNode *, MDNode *> &Cache);

  /// Find the debug info location for the start of the function.
  ///
  /// Walk up the scope chain of given debug loc and find line number info
  /// for the function.
  ///
  /// FIXME: Remove this.  Users should use DILocation/DILocalScope API to
  /// find the subprogram, and then DILocation::get().
  LLVM_ABI DebugLoc getFnDebugLoc() const;

  /// Return \c this as a bar \a MDNode.
  LLVM_ABI MDNode *getAsMDNode() const;

  /// Check if the DebugLoc corresponds to an implicit code.
  LLVM_ABI bool isImplicitCode() const;
  LLVM_ABI void setImplicitCode(bool ImplicitCode);

  bool operator==(const DebugLoc &DL) const { return Loc == DL.Loc; }
  bool operator!=(const DebugLoc &DL) const { return Loc != DL.Loc; }

  LLVM_ABI void dump() const;

  /// prints source location /path/to/file.exe:line:col @[inlined at]
  LLVM_ABI void print(raw_ostream &OS) const;

  //////////////////////////////////////////////////////////////////////////////
  // Special extra methods
  //////////////////////////////////////////////////////////////////////////////

  bool operator<(const DebugLoc &Other) const {
    return privateGet() < Other.privateGet();
  }

  DebugLoc applyMap(std::function<DILocation*(DILocation*)> Map) const {
    return DebugLoc(Map(privateGet()), std::nullopt);
  }

  void *getRawPtr() const {
    return Loc;
  }
  MDNode *getMetadataForPrintingAndParsing() const {
    return Loc;
  }
  static DebugLoc getFromDILocationForParsing(const DILocation *DIL) {
    return DebugLoc(DIL, std::nullopt);
  }

  //////////////////////////////////////////////////////////////////////////////
  // DILocation duplicate methods
  //////////////////////////////////////////////////////////////////////////////

  LLVM_ABI void print(raw_ostream &OS, const Module *M,
                      bool IsForDebug = false) const;
  LLVM_ABI void print(raw_ostream &OS, ModuleSlotTracker &MST,
                      const Module *M = nullptr, bool IsForDebug = false) const;
  LLVM_ABI void printAsOperand(raw_ostream &OS,
                               const Module *M = nullptr) const;
  LLVM_ABI void printAsOperand(raw_ostream &OS, ModuleSlotTracker &MST,
                               const Module *M = nullptr) const;
  bool isDistinct() const;

  uint64_t getAtomGroup() const;
  uint8_t getAtomRank() const;

  DebugLoc getWithoutAtom() const;

  /// Return the linkage name of Subprogram. If the linkage name is empty,
  /// return scope name (the demangled name).
  StringRef getSubprogramLinkageName() const;

  DIFile *getFile() const;
  StringRef getFilename() const;
  StringRef getDirectory() const;
  std::optional<StringRef> getSource() const;

  DebugLoc getInlinedAtLocation() const;

  unsigned getDiscriminator() const;

  static bool isPseudoProbeDiscriminator(unsigned Discriminator);

  /// Returns a new DebugLoc with updated \p Discriminator.
  DebugLoc cloneWithDiscriminator(unsigned Discriminator) const;

  /// Returns a new DebugLoc with updated base discriminator \p BD. Only the
  /// base discriminator is set in the new DebugLoc, the other encoded values
  /// are elided.
  /// If the discriminator cannot be encoded, the function returns std::nullopt.
  std::optional<DebugLoc>
  cloneWithBaseDiscriminator(unsigned BD) const;

  /// Returns the duplication factor stored in the discriminator, or 1 if no
  /// duplication factor (or 0) is encoded.
  unsigned getDuplicationFactor() const;

  /// Returns the copy identifier stored in the discriminator.
  unsigned getCopyIdentifier() const;

  /// Returns the base discriminator stored in the discriminator.
  unsigned getBaseDiscriminator() const;

  /// Returns a new DebugLoc with duplication factor \p DF * current
  /// duplication factor encoded in the discriminator. The current duplication
  /// factor is as defined by getDuplicationFactor().
  /// Returns std::nullopt if encoding failed.
  std::optional<DebugLoc>
  cloneByMultiplyingDuplicationFactor(unsigned DF) const;

  /// Return the masked discriminator value for an input discrimnator value D
  /// (i.e. zero out the (B+1)-th and above bits for D (B is 0-base).
  // Example: an input of (0x1FF, 7) returns 0xFF.
  static unsigned getMaskedDiscriminator(unsigned D, unsigned B) {
    return (D & getN1Bits(B));
  }

  /// Return the bits used for base discriminators.
  static unsigned getBaseDiscriminatorBits() { return getBaseFSBitEnd(); }

  /// Returns the base discriminator for a given encoded discriminator \p D.
  static unsigned
  getBaseDiscriminatorFromDiscriminator(unsigned D,
                                        bool IsFSDiscriminator = false) {
    // Extract the dwarf base discriminator if it's encoded in the pseudo probe
    // discriminator.
    if (isPseudoProbeDiscriminator(D)) {
      auto DwarfBaseDiscriminator =
          PseudoProbeDwarfDiscriminator::extractDwarfBaseDiscriminator(D);
      if (DwarfBaseDiscriminator)
        return *DwarfBaseDiscriminator;
      // Return the probe id instead of zero for a pseudo probe discriminator.
      // This should help differenciate callsites with same line numbers to
      // achieve a decent AutoFDO profile under -fpseudo-probe-for-profiling,
      // where the original callsite dwarf discriminator is overwritten by
      // callsite probe information.
      return PseudoProbeDwarfDiscriminator::extractProbeIndex(D);
    }

    if (IsFSDiscriminator)
      return getMaskedDiscriminator(D, getBaseDiscriminatorBits());
    return getUnsignedFromPrefixEncoding(D);
  }

  /// Raw encoding of the discriminator. APIs such as cloneWithDuplicationFactor
  /// have certain special case behavior (e.g. treating empty duplication factor
  /// as the value '1').
  /// This API, in conjunction with cloneWithDiscriminator, may be used to
  /// encode the raw values provided.
  ///
  /// \p BD: base discriminator
  /// \p DF: duplication factor
  /// \p CI: copy index
  ///
  /// The return is std::nullopt if the values cannot be encoded in 32 bits -
  /// for example, values for BD or DF larger than 12 bits. Otherwise, the
  /// return is the encoded value.
  LLVM_ABI static std::optional<unsigned>
  encodeDiscriminator(unsigned BD, unsigned DF, unsigned CI);

  /// Raw decoder for values in an encoded discriminator D.
  LLVM_ABI static void decodeDiscriminator(unsigned D, unsigned &BD,
                                           unsigned &DF, unsigned &CI);

  /// Returns the duplication factor for a given encoded discriminator \p D, or
  /// 1 if no value or 0 is encoded.
  static unsigned getDuplicationFactorFromDiscriminator(unsigned D) {
    if (EnableFSDiscriminator)
      return 1;
    D = getNextComponentInDiscriminator(D);
    unsigned Ret = getUnsignedFromPrefixEncoding(D);
    if (Ret == 0)
      return 1;
    return Ret;
  }

  /// Returns the copy identifier for a given encoded discriminator \p D.
  static unsigned getCopyIdentifierFromDiscriminator(unsigned D) {
    return getUnsignedFromPrefixEncoding(
        getNextComponentInDiscriminator(getNextComponentInDiscriminator(D)));
  }

  Metadata *getRawScope() const;
  Metadata *getRawInlinedAt() const;
};

inline raw_ostream &operator<<(raw_ostream &OS, const DebugLoc &DL) {
  DL.print(OS);
  return OS;
}

inline hash_code hash_value(const DebugLoc &Val) {
  return hash_value(Val.Loc.get());
}

/// A key class to be used in-place of DebugLoc for DenseMap keys.
struct DebugLocKey {
  MDNode *Value;
  DebugLocKey(uintptr_t Value) : Value(reinterpret_cast<MDNode*>(Value)) {}
  DebugLocKey(const DebugLoc &DL) : Value(DL.getAsMDNode()) {}
  operator DebugLoc() const {
    if (Value == DenseMapInfo<MDNode *>::getEmptyKey() || Value == DenseMapInfo<MDNode *>::getTombstoneKey())
      return DebugLoc();
    return DebugLoc(Value);
  }
  bool operator==(const DebugLocKey &Other) const { return Value == Other.Value; }
  bool operator<(const DebugLocKey &Other) const { return Value < Other.Value; }
};
template <>
struct DenseMapInfo<DebugLocKey> {
  static constexpr uintptr_t Log2MaxAlign = 12;

  static inline DebugLocKey getEmptyKey() {
    uintptr_t Val = static_cast<uintptr_t>(-1);
    Val <<= Log2MaxAlign;
    return DebugLocKey(Val);
  }

  static inline DebugLocKey getTombstoneKey() {
    uintptr_t Val = static_cast<uintptr_t>(-2);
    Val <<= Log2MaxAlign;
    return DebugLocKey(Val);
  }

  static unsigned getHashValue(DebugLocKey PtrVal) {
    return densemap::detail::mix(reinterpret_cast<uintptr_t>(PtrVal.Value));
  }

  static bool isEqual(DebugLocKey LHS, DebugLocKey RHS) { return LHS.Value == RHS.Value; }
};
inline hash_code hash_value(const DebugLocKey &Val) {
  return hash_value(Val.Value);
}

} // end namespace llvm

namespace std {
template <> struct std::hash<llvm::DebugLoc> {
  std::size_t operator()(const llvm::DebugLoc &Arg) const {
    return std::hash<llvm::hash_code>()(llvm::hash_value(Arg));
  }
};
template <> struct std::hash<llvm::DebugLocKey> {
  std::size_t operator()(const llvm::DebugLocKey &Arg) const {
    return std::hash<llvm::hash_code>()(llvm::hash_value(Arg.Value));
  }
};
} // end namespace std

#endif // LLVM_IR_DEBUGLOC_H
