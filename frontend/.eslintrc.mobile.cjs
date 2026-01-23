/**
 * ESLint Configuration for Mobile Import Protection
 *
 * This config prevents mobile code from importing desktop-specific modules,
 * specifically the auto-generated sdk.gen.ts which targets the local Python backend.
 *
 * Usage: Run `npx eslint src/mobile --config .eslintrc.mobile.cjs`
 */
module.exports = {
    root: true,
    env: {
        browser: true,
        es2020: true,
    },
    parserOptions: {
        ecmaVersion: "latest",
        sourceType: "module",
    },
    rules: {
        "no-restricted-imports": [
            "error",
            {
                patterns: [
                    {
                        group: ["@/client/*", "@/client/sdk.gen", "../client/*", "../../client/*"],
                        message:
                            "Mobile code should NOT import from @/client/sdk.gen. Use @/mobile/client instead.",
                    },
                ],
            },
        ],
    },
    overrides: [
        {
            files: ["*.ts", "*.tsx"],
            parser: "@typescript-eslint/parser",
        },
    ],
}
