/**
 * ESLint Configuration for Mobile Import Protection (ESLint 9 Flat Config)
 *
 * This config prevents mobile code from importing desktop-specific modules,
 * specifically the auto-generated sdk.gen.ts which targets the local Python backend.
 *
 * Usage: Run `npx eslint src/mobile --config eslint.mobile.config.mjs`
 */
import tsParser from "@typescript-eslint/parser";

export default [
    {
        files: ["**/*.ts", "**/*.tsx"],
        languageOptions: {
            parser: tsParser,
            parserOptions: {
                ecmaVersion: "latest",
                sourceType: "module",
            },
        },
        rules: {
            "no-restricted-imports": [
                "error",
                {
                    patterns: [
                        {
                            group: ["@/client/*", "@/client/sdk.gen", "../client/*", "../../client/*", "../../../client/*"],
                            message:
                                "❌ Mobile code should NOT import from @/client/sdk.gen (desktop SDK). Use @/mobile/client instead.",
                        },
                    ],
                },
            ],
        },
    },
];
