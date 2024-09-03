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

#include "llvm/Config/config.h"
#include "llvm/IR/TrackingMDRef.h"
#include "llvm/Support/DataTypes.h"

namespace llvm {

  class LLVMContext;
  class raw_ostream;
  class DILocation;
  class Function;

#ifdef ENABLE_DEBUGLOC_COVERAGE_TRACKING
  struct DbgLocOriginBacktrace {
    static constexpr unsigned long MaxDepth = 16;
    SmallVector<std::pair<int, std::array<void *, MaxDepth>>, 0> Stacktraces;
    DbgLocOriginBacktrace(bool ShouldCollectTrace);
    void addTrace();
  };

  // Used to represent different "kinds" of DebugLoc, expressing that a DebugLoc
  // is either ordinary, containing a valid DILocation, or otherwise describing
  // the reason why the DebugLoc does not contain a valid DILocation.
  enum class DebugLocKind : uint8_t {
    // DebugLoc should contain a valid DILocation.
    Normal,
    // DebugLoc intentionally does not have a valid DILocation; may be for a
    // compiler-generated instruction, or an explicitly dropped location.
    LineZero,
    // DebugLoc does not have a known or currently knowable source location.
    Unknown,
    // Used for instructions that we don't expect to be emitted, and so can omit
    // a valid DILocation. It is an error to try and emit a Temporary DebugLoc
    // into the line table.
    Temporary
  };

  // Extends TrackingMDNodeRef to also store a DebugLocKind and Backtrace,
  // allowing Debugify to ignore intentionally-empty DebugLocs and display the
  // code responsible for generating unintentionally-empty DebugLocs.
  class DILocAndCoverageTracking : public TrackingMDNodeRef {
  public:
    DebugLocKind Kind;
    // Currently we only need to track the Origin of this DILoc when using a
    // normal empty DebugLoc, so only collect the stack trace in those cases.
    DbgLocOriginBacktrace Origin;
    DILocAndCoverageTracking(bool NeedsStacktrace = true)
        : TrackingMDNodeRef(nullptr), Kind(DebugLocKind::Normal), Origin(NeedsStacktrace) {
    }
    // Valid or nullptr MDNode*, normal DebugLocKind
    DILocAndCoverageTracking(const MDNode *Loc)
        : TrackingMDNodeRef(const_cast<MDNode *>(Loc)),
          Kind(DebugLocKind::Normal), Origin(!Loc) {}
    DILocAndCoverageTracking(const DILocation *Loc);
    // Always nullptr MDNode*, any DebugLocKind
    DILocAndCoverageTracking(DebugLocKind Kind)
        : TrackingMDNodeRef(nullptr), Kind(Kind),
          Origin(Kind == DebugLocKind::Normal) {}
  };
  template <> struct simplify_type<DILocAndCoverageTracking> {
    using SimpleType = MDNode *;

    static MDNode *getSimplifiedValue(DILocAndCoverageTracking &MD) {
      return MD.get();
    }
  };
  template <> struct simplify_type<const DILocAndCoverageTracking> {
    using SimpleType = MDNode *;

    static MDNode *getSimplifiedValue(const DILocAndCoverageTracking &MD) {
      return MD.get();
    }
  };

  using DebugLocTrackingRef = DILocAndCoverageTracking;
#else
  using DebugLocTrackingRef = TrackingMDNodeRef;
#endif // ENABLE_DEBUGLOC_COVERAGE_TRACKING

  /// A debug info location.
  ///
  /// This class is a wrapper around a tracking reference to an \a DILocation
  /// pointer.
  ///
  /// To avoid extra includes, \a DebugLoc doubles the \a DILocation API with a
  /// one based on relatively opaque \a MDNode pointers.
  class DebugLoc {

    DebugLocTrackingRef Loc;

  public:
    DebugLoc() = default;

    /// Construct from an \a DILocation.
    DebugLoc(const DILocation *L);

    /// Construct from an \a MDNode.
    ///
    /// Note: if \c N is not an \a DILocation, a verifier check will fail, and
    /// accessors will crash.  However, construction from other nodes is
    /// supported in order to handle forward references when reading textual
    /// IR.
    explicit DebugLoc(const MDNode *N);

#if ENABLE_DEBUGLOC_COVERAGE_TRACKING
    DebugLoc(DebugLocKind Kind) : Loc(Kind) {}
    DebugLocKind getKind() const { return Loc.Kind; }
    DbgLocOriginBacktrace getOrigin() const { return Loc.Origin; }
    DebugLoc getCopied() const {
      DebugLoc NewDL = *this;
      NewDL.Loc.Origin.addTrace();
      return NewDL;
    }
#else
    DebugLoc getCopied() const {
      return *this;
    }
#endif

    static DebugLoc getTemporary();
    static DebugLoc getUnknown();
    static DebugLoc getLineZero();

    static DebugLoc getMergedLocations(ArrayRef<DebugLoc> Locs);
    static DebugLoc getMergedLocation(DebugLoc LocA, DebugLoc LocB);

    /// Get the underlying \a DILocation.
    ///
    /// \pre !*this or \c isa<DILocation>(getAsMDNode()).
    /// @{
    DILocation *get() const;
    operator DILocation *() const { return get(); }
    DILocation *operator->() const { return get(); }
    DILocation &operator*() const { return *get(); }
    /// @}

    /// Check for null.
    ///
    /// Check for null in a way that is safe with broken debug info.  Unlike
    /// the conversion to \c DILocation, this doesn't require that \c Loc is of
    /// the right type.  Important for cases like \a llvm::StripDebugInfo() and
    /// \a Instruction::hasMetadata().
    explicit operator bool() const { return Loc; }

    /// Check whether this has a trivial destructor.
    bool hasTrivialDestructor() const { return Loc.hasTrivialDestructor(); }

    enum { ReplaceLastInlinedAt = true };
    /// Rebuild the entire inlined-at chain for this instruction so that the top of
    /// the chain now is inlined-at the new call site.
    /// \param   InlinedAt    The new outermost inlined-at in the chain.
    static DebugLoc appendInlinedAt(const DebugLoc &DL, DILocation *InlinedAt,
                                    LLVMContext &Ctx,
                                    DenseMap<const MDNode *, MDNode *> &Cache);

    unsigned getLine() const;
    unsigned getCol() const;
    MDNode *getScope() const;
    DILocation *getInlinedAt() const;

    /// Get the fully inlined-at scope for a DebugLoc.
    ///
    /// Gets the inlined-at scope for a DebugLoc.
    MDNode *getInlinedAtScope() const;

    /// Rebuild the entire inline-at chain by replacing the subprogram at the
    /// end of the chain with NewSP.
    static DebugLoc
    replaceInlinedAtSubprogram(const DebugLoc &DL, DISubprogram &NewSP,
                               LLVMContext &Ctx,
                               DenseMap<const MDNode *, MDNode *> &Cache);

    /// Find the debug info location for the start of the function.
    ///
    /// Walk up the scope chain of given debug loc and find line number info
    /// for the function.
    ///
    /// FIXME: Remove this.  Users should use DILocation/DILocalScope API to
    /// find the subprogram, and then DILocation::get().
    DebugLoc getFnDebugLoc() const;

    /// Return \c this as a bar \a MDNode.
    MDNode *getAsMDNode() const { return Loc; }

    /// Check if the DebugLoc corresponds to an implicit code.
    bool isImplicitCode() const;
    void setImplicitCode(bool ImplicitCode);

    bool operator==(const DebugLoc &DL) const { return Loc == DL.Loc; }
    bool operator!=(const DebugLoc &DL) const { return Loc != DL.Loc; }

    void dump() const;

    /// prints source location /path/to/file.exe:line:col @[inlined at]
    void print(raw_ostream &OS) const;
  };

} // end namespace llvm

#endif // LLVM_IR_DEBUGLOC_H
