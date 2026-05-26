# Function-Local Metadata

### Summary

As part of the proposal for compact function-local storage of source location information, we need a mechanism to store metadata at the function/DISubprogram scope. This isn't a concept that currently exists in LLVM, and it is meaningfully distinct from other kinds of metadata, which are either printed inline, globally named, or globally numbered. Individual items of function-local metadata in this model will instead have indices that map into a list of metadata stored in a particular function - and these metadata instances also do not inherit from LLVM's `Metadata` type, as they have no need for the memory management or casting facilities.

To implement this, I propose two new different kinds of object. The first kind is "function-local metadata" (FLMD); this is a category rather than an actual C++ data type, because we don't want or need any inheritance - these objects are small, stored in an array, and are never subclassed or otherwise ambiguously-typed. The second kind is a new `Metadata` class which serves as the container for FLMD, `!DIFunctionLocalMetadata`. These objects have a few unique properties:
- The contents of `DIFunctionLocalMetadata` are arrays of function-local metadata (FLMD) objects, which are referenced by their index.
- FLMD is either *distinct*, *unique*, or *inline*, borrowing from the existing metadata terminology:
    - Unique FLMD are always uniqued, meaning that *within a particular `DIFunctionLocalMetadata`* there are no duplicates of two identical objects - a given object appears once in the storage array. When printing to IR, Unique FLMD objects can be printed in-line (meaning we print the object contents rather than a label/reference), and will be printed this way by default.
    - Distinct FLMD are not uniqued, meaning new objects are always created at a new index - there is no deduplication of identical objects. Distinct FLMD can never be printed in-line, since doing so would merge different identical instances.
    - Inline FLMD is a special case that is used for `DbgLoc`; Inline FLMD objects are *not* stored in a storage array inside `DIFunctionLocalMetadata`, but instead are objects which are stored in some other function-local context, i.e. directly stored inside an `Instruction` or as a member of another FLMD object. Inline FLMD objects can never be referenced from elsewhere (as they have no storage array and thus no index), and thus can only be printed in-line.
-  `!DIFunctionLocalMetadata` instances are only created in two contexts: as a metadata operand to a `!DISubprogram`, and as a metadata attachment to a `Function` that does not have a `!DISubprogram` but contains debug line information (via inlining).
- References to FLMD may only appear in function-local contexts, which in practice means inside another FLMD or attached to an instruction.

### IR Syntax

The IR syntax for FLMD objects is a modification of existing metadata syntax; while conceptually it is still "metadata", it has different properties and must be syntactically distinct. We represent these properties in textual IR as follows:

- FLMD is distinguished from global MD by using a double-bang (`!!`) as the prefix.
- FLMD references are "typed": unlike global MD, where *syntactically* any valid metadata number (e.g. `!10`) can be used wherever a metadata reference is accepted even if the result is *semantically* invalid IR, FLMD references cannot be resolved without a known type. Therefore, FLMD references must have a type that is either determined by its context (e.g. a field with a fixed type), or else must include an explicit type in the format `!!<type> <num>`, e.g. `!!loop 2`.
- FLMD attachments to instructions follow the existing MD attachment syntax, except that "tags" are not required due to the explicit type. For example, `<instr>, !!dbgLoc(line: 10, scope: !13)` is unambiguously a debug location attachment.

An optional "reference comments" feature is also provided to assist with reading IR, where searchable comments can be provided around references. All entries in FLMD storage arrays appear on separate lines, which end with a comment `; <index>`. When the reference comments feature is enabled, this is expanded to a reference comment: `; <functionName>@<flmdType>@<index>`. Then, when an instruction FLMD attachment is or contains an FLMD reference, we print a matching reference comment at the end of its line, allowing the referenced FLMD (and all its uses) to be found by searching for the comment text. This feature is enabled by default; passing a flag `--output-compact-debug-locations` will disable this feature, and also cause Unique FLMD to be printed as references instead of being printed in-line, which combine to significantly shorten the output.

### Transition

This change may have some impact on downstream users; the interface for creating debug line information relies on directly calling `DILocation::get`, meaning that *all* frontends that emit line information are coupled to the class that we are removing. The textual IR change will also impact any tools that parse IR. In order to make this transition relatively smooth, we'll be aiming to reach the following state:

- In-memory, `DIFunctionLocalMetadata` owns all relevant information (source locations + loops).
- A replacement interface is made available via `DebugLoc` and `DIBuilder` for creating source locations (a `clang-tidy` check could be provided to automate replacement).
- `DILocation` continues to exist and is still an `MDNode`, but it acts as a thin wrapper which contains just `DIFunctionLocalMetadata*` and `DebugLoc`, and all existing methods forward through.
- `DILocation::get` methods continue to exist with the same function signature but are deprecated, generating or fetching `DebugLoc`s from the owning `DIFunctionLocalMetadata`.
- `DILocation` does not appear in LLVM's output by default, whether Asm or Bitcode; we add a flag for one release, `--use-deprecated-dilocations`, to produce the old output (this also generates the required MDNodes for `llvm.loop` metadata); if this flag isn't passed, then the wrapper DILocations will not be printed (as they should not be referenced from anywhere else in the IR).
- As with other major format changes, an autoupgrade path for bitcode and textual IR is provided.

This should make the transition relatively straightforward for downstream consumers: existing code works with a deprecation warning, a straightforward replacement is available/automated, and the escape hatch flag can be used as a stop-gap for any parsing tools that need time to update.

### Textual IR Examples

A set of textual IR examples are provided [here](./). There are two input files, `simple.ll` and `complex.ll`, respectively representing a basic feature demonstration and a more complex "stress test" for the representation, though both are relatively small cases. For each input there are two output files, `-readable.ll` and `-compact.ll`, representing the two different presentations as described above.

### Simplified example implementation

The following is a description of the FLMD-related data types, and some sample functions; it is obviously not a complete implementation, nor are its design decisions final, and it skips past some of the edge cases (e.g. Functions without a DISubprogram that inline a Function with a DISubprogram) for the purpose of keeping the example simple. It aims instead to illustrate the shape of the design, so that its characteristics can be more easily understood.

```cpp

// Inline FLMD
class DebugLoc {
    // For both SrcLocIdx and InlinedAtIdx, we need a sentinel value to indicate
    // that no value is present. We use 0 as the sentinel value here, and use
    // Idx-1 as the real index.
    uint32_t SrcLocIdx; // FLMD reference.
    uint16_t InlinedAtIdx; // FLMD reference.
    uint16_t AtomGroup : 13;
    uint16_t AtomRank : 3;

    operator bool() { return SrcLocIdx; }
    uint32_t getSrcLocIdx() { return SrcLocIdx - 1; }
    bool isInlined() { return InlinedAtIdx; }
    uint16_t getInlinedAtIdx() { return InlinedAtIdx - 1; }
    void setInlinedAtIdx(uint16_t NewIdx) { InlinedAtIdx = NewIdx + 1; }

    // Methods that use a known context to return the contents of this DebugLoc.
    unsigned getLine(DIFunctionLocalMetadata *FunctionContext)
    DILocalScope *getScope(DIFunctionLocalMetadata *FunctionContext)
    DebugLoc getInlinedAt(DIFunctionLocalMetadata *FunctionContext)
};

// Unique FLMD
class SrcLoc {
    uint32_t Line;
    uint16_t Col;
    uint16_t ScopeIdx; // FLMD Reference.
};

// Distinct FLMD
class Loop {
    DebugLoc Start;
    DebugLoc End;
    MDNodeArray Properties;
};

// Distinct FLMD
class InlinedCallLoc {
    DebugLoc Loc;
    DIFunctionLocalMetadata *InlinedFLMD;
};

class DIFunctionLocalMetadata : public MDNode {
    // Distinct FLMD.
    SmallVector<InlinedCallLoc> InlinedCallLocs;
    SmallVector<Loop> Loops;
    // Uniqued FLMD.
    SmallVector<SrcLoc> SrcLocs;
    // NB: This "FLMD" is a single pointer that we use as Unique FLMD; we could
    // create a wrapper class if we had any motivation to define each FLMD kind
    // as a specific class, but for now we do not.
    SmallVector<DILocalScope*> Scopes;
}

unsigned DebugLoc::getLine(DIFunctionLocalMetadata *FunctionContext) {
    if (!isInlined())
        return FunctionContext->SrcLocs[getSrcLocIdx()].line;
    DIFunctionLocalMetadata *InlinedFromContext = FunctionContext->InlinedCallLocs[getInlinedAtIdx()].InlinedFLMD;
    return InlinedFromContext->SrcLocs[getSrcLocIdx()].line;
}
DILocalScope *DebugLoc::getScope(DIFunctionLocalMetadata *FunctionContext) {
    if (!isInlined()) {
        unsigned ScopeIdx = FunctionContext->SrcLocs[getSrcLocIdx()].ScopeIdx;
        return FunctionContext->Scopes[ScopeIdx];
    }
    DIFunctionLocalMetadata *InlinedFromContext = FunctionContext->InlinedCallLocs[getInlinedAtIdx()].InlinedFLMD;
    unsigned ScopeIdx = InlinedFromContext->SrcLocs[getSrcLocIdx()].ScopeIdx;
    return InlinedFromContext->Scopes[ScopeIdx];
}
DebugLoc DebugLoc::getInlinedAt(DIFunctionLocalMetadata *FunctionContext) {
    if (!isInlined())
        return DebugLoc::EMPTY;
    return FunctionContext->FunctionContext->InlinedCallLocs[getInlinedAtIdx()].Loc;
}

// Helper class for working with DebugLocs.
// NB: Since this class is quite wide, in some cases it makes sense to use this
//     class as-is, and in others it may make sense to store the context and loc
//     separately, e.g. if we have a list then it would be cheaper to use
//     SmallVector<DebugLoc> + DIFunctionLocalMetadata* rather than
//     SmallVector<DebugLocRef>.
class DebugLocRef {
    DIFunctionLocalMetadata *FLMD;
    DebugLoc Loc;
    DebugLocRef(Instruction *I) :
        FLMD(I->getFunction()->getSubprogram()->getFLMD()),
        Loc(I->getDebugLoc()) {}
    DebugLocRef(DIFunctionLocalMetadata *FLMD, DebugLoc Loc) :
        FLMD(FLMD), Loc(Loc) {}
    // Forwards methods to DebugLoc using the stored FLMD.
    unsigned getLine() {
        return Loc.getLine(FLMD);
    }
    // For DILocation methods that previously returned another DILocation, we
    // return another DebugLocRef using the same context.
    DebugLocRef getInlinedAt() {
        return DebugLocRef(FLMD, Loc.getInlinedAt(FLMD));
    }
}

/// After we have inlined \p Callee into \p Caller, generate the required
/// InlinedCallLoc entry and update the DebugLoc for each of
/// \p InlinedInstructions to refer to it.
void addInlinedDebugLocations(
        DIFunctionLocalMetadata *Caller, DIFunctionLocalMetadata *Callee,
        Instruction *Call, ArrayRef<Instruction *> InlinedInstructions) {
    DebugLoc CallLoc = Call->getDebugLoc();
    unsigned OldInlinedCallsCount = Caller->InlinedCallLocs.size();
    // If `Caller` has N existing InlinedCallLocs, the entry for `Call` will be
    // at index N, and then a copy of every InlinedCallLoc from `Caller` will be
    // appended to `Caller`.
    // Therefore, every inlined DebugLoc that had no `InlinedAtIdx` should be
    // set with `InlinedAtIdx=N`, and every inlined DebugLoc that had an
    // `InlinedAtIdx` already should be update with `InlinedAtIdx += N + 1`.
    Caller->InlinedCallLocs.push_back(CallLoc);
    auto UpdateCallLoc = [OldInlinedCallsCount](DebugLoc DL) {
        if (DL.isInlined())
            DL.setInlinedAtIdx(DL.getInlinedAtIdx() + OldInlinedCallsCount + 1);
        else
            DL.setInlinedAtIdx(OldInlinedCallsCount);
        return DL;
    };

    // Add new InlinedCallLoc and append Callee InlinedCallLocs.
    Caller->InlinedCallLocs.append(Callee->InlinedCallLocs);
    for (int NewIdx = OldInlinedCallsCount + 1,
         LastNewIdx = OldInlinedCallsCount + 1 + Callee->InlinedCallLocs.size();
         NewIdx < LastNewIdx; ++NewIdx)
    {
        Caller->InlinedCallLocs[NewIdx].Loc =
            UpdateCallLoc(Caller->InlinedCallLocs[NewIdx].Loc)
    }

    // Update InlinedAtIdxs on inlined instructions.
    for (auto *InlinedInst : InlinedInstructions)
        if (auto OldDebugLoc = InlinedInst->getDebugLoc())
            InlinedInst->setDebugLoc(UpdateCallLoc(OldDebugLoc));
}
```
