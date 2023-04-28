module.exports = {
    extends: ["next", "next/core-web-vitals"],
    parser: "@babel/eslint-parser",
    parserOptions: {
      requireConfigFile: false,
      babelOptions: {
        presets: ["next/babel"],
      },
    },
    rules: {
      // Add any custom rules here
    },
  };