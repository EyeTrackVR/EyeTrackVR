const path = require("path");
const tailwindConfigPath = path.join(__dirname, "../tailwind.config.js"); // or your own config file
require("storybook-tailwind-foundations/initialize.js").default(
    tailwindConfigPath
);

const resolve = (item) => {
    return path.join(__dirname, "../", item);
};
const { mergeConfig } = require("vite");

module.exports = {
    stories: ["../src/**/*.stories.@(js|jsx|ts|tsx)"],
    addons: ["@storybook/addon-links", "@storybook/addon-essentials"],

    framework: "@storybook/react",
    core: {
        builder: "@storybook/builder-vite",
    },

    viteFinal(config, {}) {
        return mergeConfig(config, {
            resolve: {
                alias: {
                    "@components": resolve("src/components"),
                    "@utils": resolve("src/utils"),
                    "@static": resolve("src/utils/static"),
                },
            },
            define: {
                "process.env.NODE_DEBUG": "false",
            },
        });
    },
};
