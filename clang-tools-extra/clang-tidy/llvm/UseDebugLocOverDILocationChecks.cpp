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
  auto DILocationStaticCallQualifiedMatch =
    declRefExpr(
      to(functionDecl(IsDILocationMethod, HasReplaceableName)),
      hasQualifier(hasPrefix(nestedNameSpecifier(
        specifiesNamespace(hasName("llvm"))))));

  return applyFirst({
    makeRule(
      DILocationStaticCallQualifiedMatch.bind("call"),
      changeTo(node("call"), cat("llvm::DebugLoc::", name("call"))),
      cat("use DebugLoc:: methods instead of DILocation::")),
    makeRule(
      DILocationStaticCallMatch.bind("call"),
      changeTo(node("call"), cat("DebugLoc::", name("call"))),
      cat("use DebugLoc:: methods instead of DILocation::")),
    });
}

// Variables:
// Match: Any declaration of a variable with the type DILocation* (ignoring
//        qualifiers), either as a local variable or as a class member.
// Action: Replace with non-const DebugLoc-type variable.
static RewriteRuleWith<std::string> useDebugLocVariables(bool SafeFixesOnly, bool QualifyDebugLocs) {
  auto DILocationVariableMatch = varDecl(
    hasType(pointsTo(cxxRecordDecl(hasName("::llvm::DILocation")))),
    unless(isInstantiated())
  );
  auto DILocationVariableQualifiedMatch = varDecl(
    hasTypeLoc(pointerTypeLoc(
      hasPointeeLoc(typeLoc(
        loc(qualType(
          hasDeclaration(cxxRecordDecl(hasName("::llvm::DILocation")))
        )),
        hasQualifierLoc(loc(
            specifiesNamespace(hasName("llvm"))
        ))
      ))
    ))
  );
  auto DILocationFieldMatch = fieldDecl(
    hasType(pointsTo(cxxRecordDecl(hasName("::llvm::DILocation")))),
    unless(isInstantiated())
  );
  auto DILocationParamMatch = parmVarDecl(
    hasType(pointsTo(cxxRecordDecl(hasName("::llvm::DILocation")))),
    unless(isInstantiated())
  );

  StringRef DebugLocName = QualifyDebugLocs ? "llvm::DebugLoc " : "DebugLoc ";
  auto WarnOnly = noopEdit(node("decl"));
  auto DoEdit = changeTo(node("decl"), cat("DebugLoc ", range(before(name("decl")), after(node("decl")))));
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
      DILocationVariableQualifiedMatch.bind("decl"),
      changeTo(node("decl"), cat("llvm::DebugLoc ", range(before(name("decl")), after(node("decl"))))),
      cat("use DebugLoc variables instead of DILocation*")),
    makeRule(
      DILocationVariableMatch.bind("decl"),
      changeTo(node("decl"), cat("DebugLoc ", range(before(name("decl")), after(node("decl"))))),
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
  auto IsTemplateSpecializationWithArgument = [](auto InnerMatcher) -> auto {
    return hasTypeLoc(templateSpecializationTypeLoc(
      hasAnyTemplateArgumentLoc(InnerMatcher)));
  };
  auto DILocTemplateArg = templateArgumentLoc(
    hasTypeLoc(loc(qualType(
      pointsTo(cxxRecordDecl(
        hasName("::llvm::DILocation")))))));
  auto DILocationVariableTemplVarMatch = varDecl(
    hasTypeLoc(templateSpecializationTypeLoc(
      hasAnyTemplateArgumentLoc(DILocTemplateArg.bind("templateArg"))
    )),
    unless(isInstantiated())
  );
  auto DILocationVariableTemplVarMatch2 = varDecl(
    hasTypeLoc(templateSpecializationTypeLoc(
      hasAnyTemplateArgumentLoc(templateArgumentLoc(
        hasTypeLoc(templateSpecializationTypeLoc(
          hasAnyTemplateArgumentLoc(DILocTemplateArg.bind("templateArg"))
        ))
      ))
    )),
    unless(isInstantiated())
  );
  auto DILocationVariableTemplFieldMatch = fieldDecl(
    hasTypeLoc(templateSpecializationTypeLoc(
      hasAnyTemplateArgumentLoc(DILocTemplateArg.bind("templateArg")))),
    unless(isInstantiated())
  );
  auto DILocationVariableTemplFieldMatch2 = fieldDecl(
    hasTypeLoc(templateSpecializationTypeLoc(
      hasAnyTemplateArgumentLoc(templateArgumentLoc(
        hasTypeLoc(templateSpecializationTypeLoc(
          hasAnyTemplateArgumentLoc(DILocTemplateArg.bind("templateArg"))
        ))
      ))
    )),
    unless(isInstantiated())
  );

  StringRef DebugLocName = QualifyDebugLocs ? "llvm::DebugLoc" : "DebugLoc";
  auto DoEdit = changeTo(node("templateArg"), cat(DebugLocName));
  auto Message = cat(
    "prefer DebugLoc variables instead of DILocation*; see issue #XXXXXXX"
  );

  return applyFirst({
    makeRule(DILocationVariableTemplVarMatch, DoEdit, Message),
    makeRule(DILocationVariableTemplVarMatch2, DoEdit, Message),
    makeRule(DILocationVariableTemplFieldMatch, DoEdit, Message),
    makeRule(DILocationVariableTemplFieldMatch2, DoEdit, Message),
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
