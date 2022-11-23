import { storiesOf } from "@storybook/react";
import { Button } from "./index";

export const args = {
    text: "Log",
    color: "#6f4ca1",
    onClick: () => {
        console.log("click");
    },
    shadow: "0 10px 20px -10px rgba(24, 90, 219, 0.6)",
};

storiesOf("Button/Button", module).add("Button", () => <Button {...args} />);
