const { getDefaultConfig } = require("expo/metro-config");

/** @type {import('expo/metro-config').MetroConfig} */
const config = getDefaultConfig(__dirname);

// markdown-it requires 'punycode' (a Node.js built-in removed in Node 21+).
// Metro can't resolve Node built-ins, so we map it to the npm 'punycode' package.
config.resolver.extraNodeModules = {
  ...config.resolver.extraNodeModules,
  punycode: require.resolve("punycode/"),
};

// Allow resolving from /app paths (needed for basePath support)
config.resolver.nodeModulesPaths = [
  ...(config.resolver.nodeModulesPaths || []),
];

module.exports = config;
