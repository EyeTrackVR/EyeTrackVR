"use strict";
const fs = require("fs");
const { log, logLevel } = require(process.env.LOG);
let CONFIG;

function checkConfig() {
    // if(CONFIG.scopes.length > 0){
    log(logLevel.INFO, "CORE-CONFIG", `Scopes checked`);
    CONFIG.scopes = [];
    // }
    // if(CONFIG.modules.length > 0){
    log(logLevel.INFO, "CORE-CONFIG", `Modules checked`);
    CONFIG.modules = [];
    // }
}

function writeConfig() {
    try {
        fs.writeFileSync(process.env.CONFIGFILE, JSON.stringify(CONFIG, null, 4));
        log(logLevel.FINE, "CORE-CONFIG", `Config written`);
    } catch (error) {
        log(logLevel.WARN, "CORE-CONFIG", "Failed to write to config file");
        throw error;
    }
}

function createNewConfig() {
    const config = {};
    try {
        fs.writeFileSync(process.env.CONFIG, JSON.stringify(config));
        console.log(`New Config created`);
    } catch (error) {
        console.error("Failed to create config file");
        throw error;
    }
}

module.exports = {
    initConfig: () => {
        if (!fs.existsSync(process.env.CONFIGFILE)) createNewConfig();
        try {
            CONFIG = JSON.parse(fs.readFileSync(process.env.CONFIGFILE));
            // checkConfig();
            // writeConfig();
            CONFIG.scopes = [];
        } catch (error) {
            console.error("Failed to load config file");
            throw error;
        }
        process.env.CONFIG = __filename;
        console.log(`Config handler loaded`);
    },
    CONFIG: (range) => {
        return CONFIG[range] ?? CONFIG;
    },
    reloadConfig: async () => {
        return new Promise((resolve, reject) => {
            log(logLevel.INFO, "CORE-CONFIG", `Reloading Config`);
            fs.readFile(process.env.CONFIGFILE, (err, data) => {
                if (err) {
                    log(logLevel.WARN, "CORE-CONFIG", `Failed to reload Config`);
                    reject(err);
                }
                resolve();
                CONFIG = JSON.parse(data);
            });
        });
    },
    dumpConfig: async () => {
        return new Promise((resolve, reject) => {
            log(logLevel.INFO, "CORE-CONFIG", `Dumping Config`);
            try {
                writeConfig()
                resolve();
            } catch (error) {
                log(logLevel.WARN, "CORE-CONFIG", `Failed to dump Config`);
                reject(error);
            }
            // fs.writeFile(process.env.CONFIGFILE, JSON.stringify(CONFIG, null, 4), (err) => {
            //     if (err) {
            //         log(logLevel.WARN, "CORE-CONFIG", `Failed to dump Config`);
            //         reject(err);
            //     };
            //     log(logLevel.STATUS, "CORE-CONFIG", `Config dumped`);
            //     resolve();
            // });
        });
    },
    /*
    updateConfig: async (newConfig) => {
        return new Promise((resolve, reject) => {
            log(logLevel.INFO, "CORE", `Updating Config`);            
            fs.writeFile(process.env.CONFIG, JSON.stringify(newConfig, null, 4), (err) => {
                if (err){
                    log(logLevel.ERROR, "CORE", `Failed to update Config`);
                    reject(err);
                };
                log(logLevel.INFO, "CORE", `Config updated`);
            }).then(() => {
                this.reloadConfig().then(() => {
                    log(logLevel.INFO, "CORE", `Config reloaded`);
                    resolve();
                }).catch((error) => {
                    log(logLevel.ERROR, "CORE", `Failed to update Config`);
                    reject(error);
                })
            })
        });
    }
    */
}