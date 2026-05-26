---
name: test-writer
description: Write unit tests and integration tests for code. Use when the user asks to add tests, write test cases, or improve test coverage.
---

# Test Writer

## Instructions

When writing tests:

1. Read the target source file to understand its functionality
2. Identify the testing framework already in use (check package.json or requirements.txt):
   - JavaScript/TypeScript: vitest, jest, mocha
   - Python: pytest, unittest
3. Identify testable units:
   - Public functions and methods
   - Edge cases and boundary conditions
   - Error handling paths
   - Integration points

4. Write tests following this structure:

```
describe("[ModuleName]", () => {
  describe("[functionName]", () => {
    it("should [expected behavior] when [condition]", () => {
      // Arrange
      // Act
      // Assert
    });
  });
});
```

5. Cover these test categories:
   - **Happy path** — Normal expected inputs
   - **Edge cases** — Empty, null, boundary values
   - **Error cases** — Invalid inputs, exceptions
   - **Integration** — Component interactions (if relevant)

## Rules

- Match the existing test framework and style in the project
- Use descriptive test names that explain the scenario
- One assertion per test when possible
- Don't test implementation details, test behavior
- Include setup/teardown if needed
- Place test files next to source or in `__tests__`/`tests/` per project convention
- Respond in the same language as the user
