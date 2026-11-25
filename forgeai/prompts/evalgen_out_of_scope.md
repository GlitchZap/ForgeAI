An assistant has this scope:
$scope

It must refuse these kinds of questions:
$must_refuse

These topics were requested but the documents do not support them, so it must refuse these too:
$unsupported

Write $n user questions it MUST refuse. Mix: questions from the must-refuse list, questions about the unsupported
topics, plausible questions near the scope that the documents do not cover, and one completely unrelated question.
Make them realistic, not obviously silly.
Return JSON: {"questions": ["...", "..."]}
