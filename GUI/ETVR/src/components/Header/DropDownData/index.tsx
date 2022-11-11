import {
    faDroplet,
    faEye,
    faEyeLowVision,
} from "@fortawesome/free-solid-svg-icons";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
export const DropDataData = [
    {
        name: "Blob Detection",
        icon: <FontAwesomeIcon icon={faDroplet} />,
        id: "blob",
    },
    {
        name: "One Eye",
        icon: <FontAwesomeIcon icon={faEyeLowVision} />,
        id: "oneEye",
    },
    {
        name: "Dual Eye",
        icon: <FontAwesomeIcon icon={faEye} />,
        id: "dualEye",
    },
];
