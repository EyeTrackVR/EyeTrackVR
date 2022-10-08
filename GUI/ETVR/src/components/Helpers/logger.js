"use strict";
const fs = require('fs');
const logLevel = require("./logLevels");
const Style = require('./Style');

function createLogFile(filePath) {
    try {
        if (!fs.existsSync(filePath)) {
            fs.mkdirSync(filePath.split(import.meta.Config.SEP).slice(0, -1).join(import.meta.Config.SEP), { recursive: true });
            fs.writeFileSync(filePath, "===eLog2 Log File - enjoy extended logging functionality===\n", "utf8");
            console.log(`Log file created at ${filePath}`);
            return true;
        }
    } catch (err) {
        console.log("Error creating eLog file");
        console.error(err);
        return false;
    }
}

function getMSG(level, scope, rawmsg) {
    const logTime = new Date().toISOString().replace(/T/g, ' ').slice(0, -1);
    switch (level) {
        case logLevel.SEVERE:
            return `${Style.RED}${Style.BOLD}[${logTime}] [${scope}] ${rawmsg}${Style.END}`;
        case logLevel.ERROR:
            return `${Style.RED}${logTime} [${level.def}] [${scope}] ${rawmsg.stack ?? rawmsg}${Style.END}`;
        case logLevel.WARN:
            return `${Style.YELLOW}${logTime} [${level.def}] [${scope}] ${rawmsg}${Style.END}`;
        case logLevel.STATUS:
            return `${Style.BLUE}${logTime} [${level.def}] [${scope}] ${rawmsg}${Style.END}`;
        case logLevel.INFO:
            return `${Style.WHITE}${logTime} [${level.def}] [${scope}] ${rawmsg}${Style.END}`;
        case logLevel.FINE:
            return `${Style.GREEN}${logTime} [${level.def}] [${scope}] ${rawmsg}${Style.END}`;
        case logLevel.DEBUG:
            return `${Style.PURPLE}${logTime} [${level.def}] [${scope}] ${rawmsg}${Style.END}`;
        default:
            return `${Style.CYAN}${logTime} [UNSUPPORTED LEVEL: ${level}] [${scope}] ${rawmsg}${Style.END}`;
    }
}

let logFileDest;

module.exports = {
    initLogger: () => {
        const config = require(import.meta.Config.CONFIG).CONFIG().logging;
        const initTime = new Date().toISOString().slice(0, -8).replace(/-/g, '-').replace(/T/g, '_').replace(/:/g, '.');
        logFileDest = `${config.filePath}${import.meta.Config.SEP}eLog-${initTime}.log`;

        if (config.file_active) config.file_active = createLogFile(logFileDest);
        else config.file_active = false;
    },
    log: (level, scope, rawmsg, forceConsole = false) => {
        const { logLevel, eLogEnabled, file_active, console_active } = require(import.meta.Config.CONFIG).CONFIG().logging;
        if (level.value < logLevel && import.meta.env.NODE_ENV !== "development") return;
        let msg = getMSG(level, scope, rawmsg);

        if (eLogEnabled) {
            if (file_active) {
                fs.appendFileSync(logFileDest, `${msg.slice(5, -4)}\n`, "utf8");
            }
            // if (DLOG && DBENABLED) {
            //     createLog(level.def, scope, rawmsg);
            // } else if (DLOG) {
            //     console.log(`${Style.YELLOW}[UTIL] eLog (DATABASE) is enabled but scope DATABASE is not${Style.END}`);
            //     cLog = true;
            // }
            if (console_active || (import.meta.env.NODE_ENV === "development") || forceConsole) {
                console.log(msg);
            }
        } else {
            console.log(msg);
        }
    },
    logLevel,
}