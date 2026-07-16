//===----------------------------------------------------------------------===//
//
// Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
//
//===----------------------------------------------------------------------===//

#ifndef LLVM_CLANG_TOOLS_EXTRA_CLANG_TIDY_LLVM_USEDEBUGLOCOVERDILOCATION_H
#define LLVM_CLANG_TOOLS_EXTRA_CLANG_TIDY_LLVM_USEDEBUGLOCOVERDILOCATION_H

#include "../utils/TransformerClangTidyCheck.h"

namespace clang::tidy::llvm_check {

/// Checks for uses of DILocation and replaces it with uses of DebugLoc.
/// - Replaces DILocation::* with DebugLoc::*, except for get(), getDistinct(),
///   and any MDNode methods, which only produce warnings.
class UseDebugLocStaticMethodsCheck : public utils::TransformerClangTidyCheck {
public:
  UseDebugLocStaticMethodsCheck(StringRef Name, ClangTidyContext *Context);

  bool isLanguageVersionSupported(const LangOptions &LangOpts) const override {
    return LangOpts.CPlusPlus;
  }
private:
  bool QualifyDebugLocsOption;
};
/// - Replace DILocation* local and member variable types with DebugLocs,
///   including template parameters.
/// TODO: We want to replace everything outside of a few specific locations in
///       the initial migration, but long-term we want to retain the ability to
///       manually specify DILocation variables as long as they're being used
///       appropriately; therefore, it may be preferable to make this check less
///       aggressive, only converting variables that are *initialized* by
///       DebugLocs, and relying on manual intervention (aided by the deprecated
///       implicit conversions) to handle the remaining cases. Alternatively, we
///       could make the aggressive-version a separate or option-enabled check.
class UseDebugLocVariablesCheck : public utils::TransformerClangTidyCheck {
public:
  UseDebugLocVariablesCheck(StringRef Name, ClangTidyContext *Context);

  bool isLanguageVersionSupported(const LangOptions &LangOpts) const override {
    return LangOpts.CPlusPlus;
  }
private:
  bool SafeFixesOnlyOption;
  bool QualifyDebugLocsOption;
};
/// - For DebugLoc variables, replaces methods called via operator-> with direct
///   member access, avoiding the implicit conversion to DILocation.
class UseDebugLocDirectMethodsCheck : public utils::TransformerClangTidyCheck {
public:
  UseDebugLocDirectMethodsCheck(StringRef Name, ClangTidyContext *Context);

  bool isLanguageVersionSupported(const LangOptions &LangOpts) const override {
    return LangOpts.CPlusPlus;
  }
};

/// TODO: add checks for fixing up:
///       DebugLoc DL = cast<DILocation>(...) ->
///         DebugLoc DL = DebugLoc::getFromMD(cast<DILocation>(...))
///       DebugLoc DL = nullptr ->
///         DebugLoc DL = DebugLoc()

} // namespace clang::tidy::llvm_check

#endif // LLVM_CLANG_TOOLS_EXTRA_CLANG_TIDY_LLVM_USEDEBUGLOCOVERDILOCATION_H
