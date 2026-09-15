//===- Function.cpp - Implement the Global object classes -----------------===//
//
// Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
//
//===----------------------------------------------------------------------===//
//
// This file implements function-local metadata types.
//
//===----------------------------------------------------------------------===//

#include "llvm/IR/FunctionLocalMetadata.h"
#include "llvm/IR/DebugInfoMetadata.h"

using namespace llvm;


FLIndex<uint16_t> DIFunctionLocalMetadata::getFLScopeIdx(DILocalScope *Scope) {
for (uint16_t Idx = 0; Idx < Scopes.size(); ++Idx)
    if (Scopes[Idx] == Scope)
    return Idx;
if (Scopes.size() > 0)
    assert(Scope->getSubprogram() == Scopes[0]);
Scopes.push_back(FLScope(Scope));
return Scopes.size() - 1;
}
