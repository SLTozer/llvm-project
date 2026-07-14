//===----------------------------------------------------------------------===//
//
// Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
//
//===----------------------------------------------------------------------===//

#include "UseDebugLocOverDILocationChecks.h"
#include "clang/ASTMatchers/ASTMatchers.h"
#include "clang/Basic/LLVM.h"
#include "clang/Tooling/Transformer/RangeSelector.h"
#include "clang/Tooling/Transformer/RewriteRule.h"
#include "clang/Tooling/Transformer/Stencil.h"

namespace clang::tidy::llvm_check {

using namespace ::clang::ast_matchers;
using namespace ::clang::transformer;

// Statics:
// Match: Call to a free function where the parent is ::llvm::DILocation, and
//        there exists an equivalent function in DebugLoc.
// Action: Replace "DILocation" text with "DebugLoc".
static RewriteRuleWith<std::string> useDebugLocStaticCalls(bool QualifyDebugLocs) {
  auto HasReplaceableName = hasAnyName(
    "isPseudoProbeDiscriminator",
    "getMergedLocation",
    "getMergedLocations", 
    "getMaskedDiscriminator",
    "getBaseDiscriminatorBits",
    "getBaseDiscriminatorFromDiscriminator",
    "encodeDiscriminator",
    "decodeDiscriminator",
    "getDuplicationFactorFromDiscriminator",
    "getCopyIdentifierFromDiscriminator",
    "get",
    "getDistinct");
  auto IsDILocationMethod = hasParent(cxxRecordDecl(
    hasName("::llvm::DILocation")));
  auto DILocationStaticCallMatch =
    declRefExpr(
      to(functionDecl(IsDILocationMethod, HasReplaceableName)));

  StringRef DebugLocName = QualifyDebugLocs ? "llvm::DebugLoc::" :  "DebugLoc::";

  return makeRule(
    DILocationStaticCallMatch.bind("call"),
    changeTo(node("call"), cat(DebugLocName, name("call"))),
    cat("use DebugLoc:: methods instead of DILocation::"));
}

// Variables:
// Match: Any declaration of a variable with the type DILocation* (ignoring
//        qualifiers), either as a local variable or as a class member.
// Action: Replace with non-const DebugLoc-type variable.
static RewriteRuleWith<std::string> useDebugLocVariables(bool SafeFixesOnly, bool QualifyDebugLocs) {
  auto DILocationVariableMatch = varDecl(
    hasType(pointsTo(cxxRecordDecl(hasName("::llvm::DILocation"))))
  );
  auto DILocationFieldMatch = fieldDecl(
    hasType(pointsTo(cxxRecordDecl(hasName("::llvm::DILocation"))))
  );
  auto DILocationParamMatch = parmVarDecl(
    hasType(pointsTo(cxxRecordDecl(hasName("::llvm::DILocation"))))
  );

  StringRef DebugLocName = QualifyDebugLocs ? "llvm::DebugLoc " : "DebugLoc ";
  auto WarnOnly = noopEdit(node("decl"));
  auto DoEdit = changeTo(node("decl"), cat(DebugLocName, range(before(name("decl")), after(node("decl")))));
  auto ParamRule = SafeFixesOnly
    ? makeRule(
        DILocationParamMatch.bind("decl"),
        WarnOnly,
        cat("use DebugLoc variables instead of DILocation*"))
    : makeRule(
        DILocationParamMatch.bind("decl"),
        DoEdit,
        cat("use DebugLoc variables instead of DILocation*"));

  return applyFirst({
    ParamRule,
    makeRule(
      DILocationVariableMatch.bind("decl"),
      DoEdit,
      cat("use DebugLoc variables instead of DILocation*")),
    makeRule(
      DILocationFieldMatch.bind("decl"),
      DoEdit,
      cat("use DebugLoc variables instead of DILocation*")),
  });
}

// TemplateVariables:
// Match: Any use of DILocation* as a template argument.
// Action: Replace "DILocation" with "DebugLoc".
//         If SafeFixesOnly, then only non-nested uses in non-parameter
//         variables or fields are changed; others are warnings only.
static RewriteRuleWith<std::string> useDebugLocTemplateVariables(bool SafeFixesOnly, bool QualifyDebugLocs) {
  auto DILocationVariableTemplVarMatch = varDecl(
    hasTypeLoc(templateSpecializationTypeLoc(
      hasAnyTemplateArgumentLoc(templateArgumentLoc(
        hasTypeLoc(loc(qualType(              
          pointsTo(cxxRecordDecl(
            hasName("::llvm::DILocation"))))))).bind("templateArg")))),
    unless(parmVarDecl())
  );
  auto DILocationVariableTemplFieldMatch = fieldDecl(
    hasTypeLoc(templateSpecializationTypeLoc(
      hasAnyTemplateArgumentLoc(templateArgumentLoc(
        hasTypeLoc(loc(qualType(              
          pointsTo(cxxRecordDecl(
            hasName("::llvm::DILocation"))))))).bind("templateArg"))))
  );
  auto DILocationVariableTemplAnyMatch = templateArgumentLoc(
    hasTypeLoc(loc(qualType(              
      pointsTo(cxxRecordDecl(
        hasName("::llvm::DILocation"))))))).bind("templateArg");

  StringRef DebugLocName = QualifyDebugLocs ? "llvm::DebugLoc " : "DebugLoc ";
  auto DoEdit = changeTo(node("templateArg"), cat(DebugLocName));
  auto WarnOnly = noopEdit(node("templateArg"));
  auto AnyRule = SafeFixesOnly
    ? makeRule(
        DILocationVariableTemplAnyMatch,
        WarnOnly,
        cat("use DebugLoc variables instead of DILocation*"))
    : makeRule(
        DILocationVariableTemplAnyMatch,
        DoEdit,
        cat("use DebugLoc variables instead of DILocation*"));

  return applyFirst({
    makeRule(
      DILocationVariableTemplVarMatch,
      DoEdit,
      cat("use DebugLoc variables instead of DILocation*")),
    makeRule(
      DILocationVariableTemplFieldMatch,
      DoEdit,
      cat("use DebugLoc variables instead of DILocation*")),
    AnyRule,
  });
}

// Replacee DebugLoc->
// Match: All uses of operator-> from DebugLoc.
// Action: Replace `->` with `.`, except for calls to MDNode methods, which
//         will just produce a warning.
static RewriteRuleWith<std::string> avoidDebugLocArrows() {
  auto HasReplaceableName = hasAnyName(
    "getAtomGroup",
    "getAtomRank",
    "getWithoutAtom",
    "getLine",
    "getColumn",
    "getScope",
    "getSubprogramLinkageName",
    "getInlinedAt",
    "isImplicitCode",
    "setImplicitCode",
    "getFile",
    "getFilename",
    "getDirectory",
    "getSource",
    "getInlinedAtLocation",
    "getInlinedAtScope",
    "getDiscriminator",
    "cloneWithDiscriminator",
    "cloneWithBaseDiscriminator",
    "getDuplicationFactor",
    "getCopyIdentifier",
    "getBaseDiscriminator",
    "cloneByMultiplyingDuplicationFactor"
  );

  auto DebugLocArrowMatch = cxxMemberCallExpr(
    callee(memberExpr(
      isArrow(),
      member(HasReplaceableName)).bind("member")),
    on(
      cxxOperatorCallExpr(
        hasOverloadedOperatorName("->"),
        callee(cxxMethodDecl(ofClass(hasName("::llvm::DebugLoc")))),
        hasArgument(0, expr().bind("base")))));
  return makeRule(
    DebugLocArrowMatch,
    changeTo(node("member"), cat(node("base"), ".", member("member"))),
    cat("use `.` instead of `->` with DebugLoc to avoid implicit casts to DILocation")
  );
}

UseDebugLocStaticMethodsCheck::UseDebugLocStaticMethodsCheck(StringRef Name,
                                                   ClangTidyContext *Context)
    : TransformerClangTidyCheck(Name, Context),
      QualifyDebugLocsOption(Options.get("QualifyDebugLocs", true)) {
  setRule(useDebugLocStaticCalls(QualifyDebugLocsOption));
}
UseDebugLocVariablesCheck::UseDebugLocVariablesCheck(StringRef Name,
                                                   ClangTidyContext *Context)
    : TransformerClangTidyCheck(Name, Context),
    SafeFixesOnlyOption(Options.get("SafeFixesOnly", false)),
    QualifyDebugLocsOption(Options.get("QualifyDebugLocs", true)) {
  setRule(applyFirst({
      useDebugLocVariables(SafeFixesOnlyOption, QualifyDebugLocsOption),
      useDebugLocTemplateVariables(SafeFixesOnlyOption, QualifyDebugLocsOption),
  }));
}
UseDebugLocDirectMethodsCheck::UseDebugLocDirectMethodsCheck(StringRef Name,
                                                   ClangTidyContext *Context)
    : TransformerClangTidyCheck(avoidDebugLocArrows(), Name, Context) {
}

} // namespace clang::tidy::llvm_check
