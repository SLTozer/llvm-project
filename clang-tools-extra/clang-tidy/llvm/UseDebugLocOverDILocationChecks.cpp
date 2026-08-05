//===----------------------------------------------------------------------===//
//
// Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
//
//===----------------------------------------------------------------------===//

#include "UseDebugLocOverDILocationChecks.h"
#include "clang/AST/DeclCXX.h"
#include "clang/AST/TemplateBase.h"
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
static RewriteRuleWith<std::string> useDebugLocStaticCalls() {
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
static RewriteRuleWith<std::string> useDebugLocVariables(bool SafeFixesOnly) {
  auto DILocationVariableMatch = varDecl(
    hasTypeLoc(pointerTypeLoc(
      hasPointeeLoc(typeLoc(
        loc(qualType(
          hasDeclaration(cxxRecordDecl(hasName("::llvm::DILocation")))
        ))
      ))
    ).bind("varType")),
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
    ).bind("varType"))
  );
  auto DILocationFieldMatch = fieldDecl(
    hasTypeLoc(pointerTypeLoc(
      hasPointeeLoc(typeLoc(
        loc(qualType(
          hasDeclaration(cxxRecordDecl(hasName("::llvm::DILocation")))
        ))
      ))
    ).bind("varType")),
    unless(isInstantiated())
  );
  auto DILocationFieldQualifiedMatch = fieldDecl(
    hasTypeLoc(pointerTypeLoc(
      hasPointeeLoc(typeLoc(
        loc(qualType(
          hasDeclaration(cxxRecordDecl(hasName("::llvm::DILocation")))
        )),
        hasQualifierLoc(loc(
            specifiesNamespace(hasName("llvm"))
        ))
      ))
    ).bind("varType"))
  );

  // Replace the entire type; that this drops cv-qualifiers is intentional,
  // since we don't generally want to use `const DebugLoc` types.
  auto DoEdit = [](StringRef TypeString) -> auto {
    return changeTo(node("varType"), cat(TypeString));
  };
  auto Message = cat(
    "prefer DebugLoc variables instead of DILocation*; see LLVM issue #XXXXXX"
  );

  return applyFirst({
    makeRule(DILocationVariableQualifiedMatch,
                 DoEdit("llvm::DebugLoc "),
                 Message),
    makeRule(DILocationFieldQualifiedMatch,
                 DoEdit("llvm::DebugLoc "),
                 Message),
    makeRule(DILocationVariableMatch,
                 DoEdit("DebugLoc "),
                 Message),
    makeRule(DILocationFieldMatch,
                 DoEdit("DebugLoc "),
                 Message),
  });
}

// Replace `auto *Var`, where `auto` resolves to `DILocation`, with just `auto Var`
static RewriteRuleWith<std::string> avoidPointersInAutoDILocationVars() {
  auto DILocationAutoVariableMatch = varDecl(
    hasTypeLoc(pointerTypeLoc(
      hasPointeeLoc(loc(autoType(
        hasDeducedType(qualType(
          hasDeclaration(cxxRecordDecl(hasName("::llvm::DILocation")))
        ))
      )))
    ).bind("varType")),
    unless(isInstantiated())
  );

  return makeRule(
    DILocationAutoVariableMatch,
      changeTo(node("varType"), cat("auto ")),
      cat(
      "rewrite DILocation-typed auto* variables to auto to simplify automatic "
      "rewriting; see LLVM issue #XXXXXX"
    ));
}

// TemplateVariables: updates 
// TODO: Somewhat annoying+inefficient that we have to split this up into 8
// different rules (each combination of var/field, qualified/unqualified, and
// top-level template arg vs one level nested); unifying on one or more of these
// would be ideal, possibly just mashing them together with anyOf?
// TODO: This only deals with DILocation template args at the first or second
// level of a nested template specialization.
static RewriteRuleWith<std::string> useDebugLocTemplateVariables(bool SafeFixesOnly) {
  // auto IsTemplateSpecializationWithArgument = [](const auto &InnerMatcher) -> auto {
  //   return hasTypeLoc(templateSpecializationTypeLoc(
  //     hasAnyTemplateArgumentLoc(InnerMatcher)));
  // };
  auto DILocTemplateArg = templateArgumentLoc(
    hasTypeLoc(
      pointerTypeLoc(
        hasPointeeLoc(typeLoc(
          loc(qualType(
            hasDeclaration(cxxRecordDecl(hasName("::llvm::DILocation")))
          ))
        ))
      )
    ));
  auto QualifiedDILocTemplateArg = templateArgumentLoc(
    hasTypeLoc(
      pointerTypeLoc(
        hasPointeeLoc(typeLoc(
          loc(qualType(
            hasDeclaration(cxxRecordDecl(hasName("::llvm::DILocation")))
          )),
          hasQualifierLoc(loc(
              specifiesNamespace(hasName("llvm"))
          ))
        ))
      )
    ));
  // auto DILocationVariableTemplVarMatch = varDecl(
  //   IsTemplateSpecializationWithArgument(DILocTemplateArg.bind("templateArg")),
  //   unless(isInstantiated())
  // );
  // auto DILocationVariableTemplVarRefMatch = varDecl(
  //   hasTypeLoc(referenceTypeLoc(hasReferentLoc(
  //     templateSpecializationTypeLoc(hasAnyTemplateArgumentLoc(DILocTemplateArg.bind("templateArg")))
  //   ))),
  //   unless(isInstantiated())
  // );
  // auto DILocationVariableTemplVarQualifiedMatch = varDecl(
  //   IsTemplateSpecializationWithArgument(
  //     QualifiedDILocTemplateArg.bind("templateArg")
  //   ),
  //   unless(isInstantiated())
  // );
  // auto DILocationVariableTemplVarMatch2 = varDecl(
  //   IsTemplateSpecializationWithArgument(templateArgumentLoc(
  //     IsTemplateSpecializationWithArgument(DILocTemplateArg.bind("templateArg"))
  //   )),
  //   unless(isInstantiated())
  // );
  // auto DILocationVariableTemplVarQualifiedMatch2 = varDecl(
  //   IsTemplateSpecializationWithArgument(templateArgumentLoc(
  //     IsTemplateSpecializationWithArgument(
  //       QualifiedDILocTemplateArg.bind("templateArg")
  //     )
  //   )),
  //   unless(isInstantiated())
  // );
  // auto DILocationVariableTemplFieldMatch = fieldDecl(
  //   IsTemplateSpecializationWithArgument(DILocTemplateArg.bind("templateArg")),
  //   unless(isInstantiated())
  // );
  // auto DILocationVariableTemplFieldQualifiedMatch = fieldDecl(
  //   IsTemplateSpecializationWithArgument(
  //     QualifiedDILocTemplateArg.bind("templateArg")
  //   ),
  //   unless(isInstantiated())
  // );
  // auto DILocationVariableTemplFieldMatch2 = fieldDecl(
  //   IsTemplateSpecializationWithArgument(templateArgumentLoc(
  //     IsTemplateSpecializationWithArgument(DILocTemplateArg.bind("templateArg"))
  //   )),
  //   unless(isInstantiated())
  // );
  // auto DILocationVariableTemplFieldQualifiedMatch2 = fieldDecl(
  //   IsTemplateSpecializationWithArgument(templateArgumentLoc(
  //     IsTemplateSpecializationWithArgument(
  //       QualifiedDILocTemplateArg.bind("templateArg")
  //     )
  //   )),
  //   unless(isInstantiated())
  // );

  auto TemplateSpecializationWithArgument = [](const auto &InnerMatcher) -> auto {
    return templateSpecializationTypeLoc(
      hasAnyTemplateArgumentLoc(InnerMatcher));
  };
  auto SingleLevelMatchOrRef = [&](const auto &TemplateArgMatcher) -> auto {
    return anyOf(
      hasTypeLoc(TemplateSpecializationWithArgument(
        TemplateArgMatcher.bind("templateArg")
      )),
      hasTypeLoc(referenceTypeLoc(hasReferentLoc(
        TemplateSpecializationWithArgument(
          TemplateArgMatcher.bind("templateArg")
        )
      )))
    );
  };
  auto SecondLevelMatchOrRef = [&](const auto &TemplateArgMatcher) -> auto {
    return anyOf(
      hasTypeLoc(TemplateSpecializationWithArgument(
        templateArgumentLoc(hasTypeLoc(TemplateSpecializationWithArgument(
          TemplateArgMatcher.bind("templateArg")
        )))
      )),
      hasTypeLoc(referenceTypeLoc(hasReferentLoc(
        TemplateSpecializationWithArgument(
          templateArgumentLoc(hasTypeLoc(TemplateSpecializationWithArgument(
            TemplateArgMatcher.bind("templateArg")
          )))
        )
      )))
    );
  };
  auto AnyMatchOrRef = [&](const auto &InnerMatcher) -> auto {
    return anyOf(
      SingleLevelMatchOrRef(InnerMatcher), SecondLevelMatchOrRef(InnerMatcher));
  };
  auto DILocationTemplVarNonQualifiedMatch = 
    varDecl(
      AnyMatchOrRef(DILocTemplateArg),
      unless(isInstantiated()));
  auto DILocationTemplFieldNonQualifiedMatch = 
    fieldDecl(
      AnyMatchOrRef(DILocTemplateArg),
      unless(isInstantiated()));
  auto DILocationTemplAliasNonQualifiedMatch = 
    typeAliasDecl(
      AnyMatchOrRef(DILocTemplateArg),
      unless(isInstantiated()));
  auto DILocationTemplVarQualifiedMatch =
    varDecl(
      AnyMatchOrRef(QualifiedDILocTemplateArg),
      unless(isInstantiated()));
  auto DILocationTemplFieldQualifiedMatch =
    fieldDecl(
      AnyMatchOrRef(QualifiedDILocTemplateArg),
      unless(isInstantiated()));
  auto DILocationTemplAliasQualifiedMatch =
    typeAliasDecl(
      AnyMatchOrRef(QualifiedDILocTemplateArg),
      unless(isInstantiated()));

  auto DoEdit = changeTo(node("templateArg"), cat("DebugLoc"));
  auto DoEditQualified = changeTo(node("templateArg"), cat("llvm::DebugLoc"));
  auto Message = cat(
    "prefer DebugLoc variables instead of DILocation*; see LLVM issue #XXXXXX"
  );

  return applyFirst({
    makeRule(DILocationTemplVarQualifiedMatch, DoEditQualified, Message),
    makeRule(DILocationTemplFieldQualifiedMatch, DoEditQualified, Message),
    makeRule(DILocationTemplAliasQualifiedMatch, DoEditQualified, Message),
    makeRule(DILocationTemplVarNonQualifiedMatch, DoEdit, Message),
    makeRule(DILocationTemplFieldNonQualifiedMatch, DoEdit, Message),
    makeRule(DILocationTemplAliasNonQualifiedMatch, DoEdit, Message),
  });
}


static RewriteRuleWith<std::string> useDebugLocReturnTypes(bool SafeFixesOnly) {
  auto DILocationReturnMatch = functionDecl(
    hasReturnTypeLoc(
      typeLoc(
        loc(pointsTo(cxxRecordDecl(hasName("::llvm::DILocation"))))
      ).bind("returnType")
    ),
    unless(isInstantiated())
  );

  auto DILocationReturnTemplMatch = functionDecl(
    hasReturnTypeLoc(
      typeLoc(
        templateSpecializationTypeLoc(
          hasAnyTemplateArgumentLoc(
            templateArgumentLoc(
              hasTypeLoc(
                pointerTypeLoc(
                  hasPointeeLoc(typeLoc(
                    loc(qualType(
                      hasDeclaration(cxxRecordDecl(hasName("::llvm::DILocation")))
                    ))
                  ))
                ).bind("returnType")
              )
            )
          )
        )
      )
    ),
    unless(isInstantiated())
  );
  auto DILocationReturnQualifiedMatch = functionDecl(
    hasReturnTypeLoc(pointerTypeLoc(
      hasPointeeLoc(typeLoc(
        loc(qualType(
          hasDeclaration(cxxRecordDecl(hasName("::llvm::DILocation")))
        )),
        hasQualifierLoc(loc(
            specifiesNamespace(hasName("llvm"))
        ))
      ))
    ).bind("returnType"))
  );

  // Replace the entire type; that this drops cv-qualifiers is intentional,
  // since we don't generally want to use `const DebugLoc` types.
  auto DoEdit = [](StringRef TypeString) -> auto {
    return changeTo(
      node("returnType"),
      cat(TypeString));
  };
  auto Message = cat(
    "prefer DebugLoc return types instead of DILocation*; see LLVM issue #XXXXXX"
  );


  return applyFirst({
    makeRule(DILocationReturnQualifiedMatch,
                 DoEdit("llvm::DebugLoc "),
                 Message),
    makeRule(DILocationReturnMatch,
                 DoEdit("DebugLoc "),
                 Message),
    makeRule(DILocationReturnTemplMatch,
                 DoEdit("DebugLoc "),
                 Message),
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
    "getRawScope",
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
    "cloneByMultiplyingDuplicationFactor",
    "getContext",
    "dump",
    "print",
    "printAsOperand"
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

static RewriteRuleWith<std::string> avoidDebugLocDILocationRoundtrip() {
  auto DebugLocRoundtrip = cxxConstructExpr(
    hasDeclaration(cxxConstructorDecl(hasName("DebugLoc"))),
    hasArgument(0, cxxMemberCallExpr(
      hasDeclaration(cxxMethodDecl(hasName("DebugLoc::get"))),
      on(expr().bind("origDL"))
    ).bind("getCall"))
  );
  return makeRule(
    DebugLocRoundtrip,
    changeTo(node("getCall"), cat(node("origDL"))),
    cat("undesirable DebugLoc->DILocation->DebugLoc roundtrip")
  );
}

static RewriteRuleWith<std::string> avoidDebugLocGetForBool() {
  auto DebugLocGetToBool = implicitCastExpr(
    hasImplicitDestinationType(booleanType()),
    hasSourceExpression(cxxMemberCallExpr(
      hasDeclaration(cxxMethodDecl(hasName("DebugLoc::get"))),
      on(expr().bind("origDL"))
    ).bind("getCall"))
  );
  return makeRule(
    DebugLocGetToBool,
    changeTo(node("getCall"), cat(node("origDL"))),
    cat("use DebugLoc::operator bool() instead of use of (bool)DebugLoc.get()")
  );
}

static RewriteRuleWith<std::string> removeConstCastDebugLoc() {
  auto ExplicitCastDebugLocToDILoc = castExpr(
    explicitCastExpr(
      hasDestinationType(qualType(
        pointsTo(qualType(
          hasDeclaration(cxxRecordDecl(
            hasName("::llvm::DILocation")
          ))
        ))
      ))
    ),
    hasSourceExpression(expr(
      hasType(cxxRecordDecl(hasName("::llvm::DebugLoc")))
    ).bind("castValue"))
  );
  return makeRule(
    ExplicitCastDebugLocToDILoc,
    changeTo(node("getCall"), cat(node("origDL"))),
    cat("use DebugLoc::operator bool() instead of use of (bool)DebugLoc.get()")
  );
}

UseDebugLocStaticMethodsCheck::UseDebugLocStaticMethodsCheck(StringRef Name,
                                                   ClangTidyContext *Context)
    : TransformerClangTidyCheck(useDebugLocStaticCalls(), Name, Context) {}
UseDebugLocVariablesCheck::UseDebugLocVariablesCheck(StringRef Name,
                                                   ClangTidyContext *Context)
    : TransformerClangTidyCheck(Name, Context),
    SafeFixesOnlyOption(Options.get("SafeFixesOnly", false)) {
  setRule(applyFirst({
      avoidPointersInAutoDILocationVars(),
      useDebugLocVariables(SafeFixesOnlyOption),
      useDebugLocTemplateVariables(SafeFixesOnlyOption),
      useDebugLocReturnTypes(SafeFixesOnlyOption),
  }));
}
UseDebugLocDirectMethodsCheck::UseDebugLocDirectMethodsCheck(StringRef Name,
                                                   ClangTidyContext *Context)
    : TransformerClangTidyCheck(applyFirst({
      avoidDebugLocArrows(), avoidDebugLocDILocationRoundtrip(), avoidDebugLocGetForBool()
    }), Name, Context) {}

} // namespace clang::tidy::llvm_check
