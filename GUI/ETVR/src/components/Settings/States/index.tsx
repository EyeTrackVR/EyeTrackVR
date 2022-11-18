const Settings = [{}];

const GeneralSettings = [
    {
        name: "Flip Left Eye X Axis",
        label: "",
        tooltip: "",
        type: "",
    },
    {
        name: "Flip Right Eye X Axis",
        label: "",
        tooltip: "",
        type: "",
    },
    {
        name: "Flip Y Axis",
        label: "",
        tooltip: "",
        type: "",
    },
    {
        name: "Dual Eye FallOff",
        label: "",
        tooltip: "",
        type: "",
    },
    {
        name: "Sync Blinks (disables winking)",
        label: "",
        tooltip: "",
        type: "",
    },
];
const AlgoSettings = [
    [
        {
            name: "Min Blob Size",
            id: "min_blob_size",
            min: 0,
            max: 100,
            value: 10,
            step: 1,
            tooltip: "sets the minimum size of the blob",
        },
        {
            name: "Max Blob Size",
            id: "max_blob_size",
            min: 0,
            max: 100,
            value: 10,
            step: 1,
            tooltip: "sets the maximum size of the blob",
        },
    ],
    [
        {
            name: "",
            label: "",
            tooltip: "",
            type: "",
        },
    ],
];
const FilterParams = [
    {
        name: "",
        label: "",
        tooltip: "",
        type: "",
    },
];
const OSCSettings = [
    {
        name: "",
        label: "",
        tooltip: "",
        type: "",
    },
];

export { Settings, GeneralSettings, AlgoSettings, FilterParams, OSCSettings };
