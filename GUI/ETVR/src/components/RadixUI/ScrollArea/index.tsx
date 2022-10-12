import * as ScrollAreaPrimitive from "@radix-ui/react-scroll-area";
import { styled } from "@stitches/react";
/* import React from "react"; */
/* import styles from "./index.module.scss"; */

const SCROLLBAR_SIZE = 10;

const StyledScrollArea = styled(ScrollAreaPrimitive.Root, {
    display: "flex",
    flexDirection: "column",
    alignItems: "flexStart",
    justifyContent: "center",
    marginLeft: "6rem",
    marginTop: "2rem",
    marginRight: "2rem",
    backgroundColor: "#252536ba",
    borderColor: "#9A6998",
    borderStyle: "inset",
    borderWidth: "0.1rem",
    borderRadius: "30px",
    padding: "1rem",
    boxShadow:
        "rgba(50, 50, 93, 0.25) 0px 30px 60px -12px inset, rgba(0, 0, 0, 0.3) 0px 18px 36px -18px inset",
});

const StyledViewport = styled(ScrollAreaPrimitive.Viewport, {
    width: "100%",
    height: "100%",
    borderRadius: "inherit",
});

const StyledScrollbar = styled(ScrollAreaPrimitive.Scrollbar, {
    display: "flex",
    // ensures no selection
    userSelect: "none",
    // disable browser handling of all panning and zooming gestures on touch devices
    touchAction: "none",
    padding: 2,
    background: "2B2B2B",
    transition: "background 160ms ease-out",
    "&:hover": { background: "#3F3F3F" },
    '&[data-orientation="vertical"]': { width: SCROLLBAR_SIZE },
    '&[data-orientation="horizontal"]': {
        flexDirection: "column",
        height: SCROLLBAR_SIZE,
    },
});

const StyledThumb = styled(ScrollAreaPrimitive.Thumb, {
    flex: 1,
    background: "#3F3F3F",
    borderRadius: SCROLLBAR_SIZE,
    // increase target size for touch devices https://www.w3.org/WAI/WCAG21/Understanding/target-size.html
    position: "relative",
    "&::before": {
        content: '""',
        position: "absolute",
        top: "50%",
        left: "50%",
        transform: "translate(-50%, -50%)",
        width: "100%",
        height: "100%",
        minWidth: 44,
        minHeight: 44,
    },
});

const StyledCorner = styled(ScrollAreaPrimitive.Corner, {
    background: "#3F3F3F",
});

// Exports
export const ScrollArea = StyledScrollArea;
export const ScrollAreaViewport = StyledViewport;
export const ScrollAreaScrollbar = StyledScrollbar;
export const ScrollAreaThumb = StyledThumb;
export const ScrollAreaCorner = StyledCorner;

/** 
 * Usage:
 * import { violet, mauve } from "@radix-ui/colors";
 * import * as ScrollAreaCustom from "@src/components/RadixUI/ScrollArea";
 * import { styled } from "@stitches/react";

const Box = styled("div", {});
const Text = styled("div", {
    color: violet.violet11,
    fontSize: 15,
    lineHeight: "18px",
    fontWeight: 500,
});

const Tag = styled("div", {
    color: mauve.mauve12,
    fontSize: 13,
    lineHeight: "18px",
    marginTop: 10,
    borderTop: `1px solid ${mauve.mauve6}`,
    paddingTop: 10,
});

export function ScrollAreaCustom() {
    return (
     <ScrollAreaCustom.ScrollArea>
        <ScrollAreaCustom.ScrollAreaViewport
            css={{ backgroundColor: "#252535" }}
        >
            <Box
                style={{
                    padding: "15px 20px",
                }}
            >
                <Text>Tags</Text>
                <Tag>Tag 1</Tag>
                <Tag>Tag 2</Tag>
                <Tag>Tag 3</Tag>
            </Box>
        </ScrollAreaCustom.ScrollAreaViewport>
        <ScrollAreaCustom.ScrollAreaScrollbar orientation="vertical">
            <ScrollAreaCustom.ScrollAreaThumb />
        </ScrollAreaCustom.ScrollAreaScrollbar>
        <ScrollAreaCustom.ScrollAreaScrollbar orientation="horizontal">
            <ScrollAreaCustom.ScrollAreaThumb />
        </ScrollAreaCustom.ScrollAreaScrollbar>
        <ScrollAreaCustom.ScrollAreaCorner />
    </ScrollAreaCustom.ScrollArea>
    );
}
*/
