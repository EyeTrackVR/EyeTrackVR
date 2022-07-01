var port,
  textEncoder,
  writableStreamClosed,
  writer,
  historyIndex = -1;
const lineHistory = [];

/* ASCII Art*/
var neofetch_data = `\r\n                  @@@@@@                    dev@EyeTrackVR\r\n              @@@@@@@@@@@            @@@    -------------- \r\n            @@@@@@@@@@@@      @@@@@@@@@@@   OS Arch Linux x86_64\r\n          @@@@@@@@@@@@@   @@@@@@@@@@@@@@    Host Your PC\r\n        @@@@@@@#         ,@@@@@@@@@@@@@     Kernel 5.5.13-arch1-1\r\n          ,@@@@@@@@@@@@@@@  @@@@@@@@        Uptime 69 days, 42 hours, 21 mins\r\n      @@@@@@@@@@@@@@@@@@@@@@@@ @@@@@        Shell bash 5.0.16\r\n  @@@@@@@@                @@@@@             CPU AMD Ryzen Threadripper PRO\r\n@@@                        @@@@@            Memory 3869MiB \/ 5229MiB\r\n              @@@@@@        @@@@            \r\n    @@@     @@@@@@@@@\/      @@@@@           \r\n    ,@@@.     @@@@@@((@     @@@@(           \r\n    \/\/@@@        *\/  @@@@  @@@@@            \r\n    @@@(                @@@@@@@             \r\n    @@@  @          @@@@@@@@@               \r\n        @@@@@@@@@@@@@@@@@                   \r\n        @@@@@@@@@@@@@&`;

var contributors = [
  `  _____           _                _       \r\n |  __ \\         | |              | |      \r\n | |__) | __ ___ | |__  _   _ _ __| |_ ____\r\n |  ___\/ \'__\/ _ \\| \'_ \\| | | | \'__| __|_  \/\r\n | |   | | | (_) | | | | |_| | |  | |_ \/ \/ \r\n |_|   |_|  \\___\/|_| |_|\\__,_|_|   \\__\/___|\r\n                                           `,
  `   _____                                     \r\n  / ____|                                    \r\n | (___  _   _ _ __ ___  _ __ ___   ___ _ __ \r\n  \\___ \\| | | | '_ \` _ \\| '_ \` _ \\ / _ \\ '__|\r\n  ____) | |_| | | | | | | | | | | |  __/ |   \r\n |_____/ \\__,_|_| |_| |_|_| |_| |_|\\___|_|   \r\n                                             `,
  `  ______                  _______ _    _ ______ _                \r\n |___  \/                 |__   __| |  | |  ____| |               \r\n    \/ \/ __ _ _ __  _____   _| |  | |__| | |__  | |__   __ _ _ __ \r\n   \/ \/ \/ _\` | \'_ \\|_  \/ | | | |  |  __  |  __| | \'_ \\ \/ _\` | \'__|\r\n  \/ \/_| (_| | | | |\/ \/| |_| | |  | |  | | |____| |_) | (_| | |   \r\n \/_____\\__,_|_| |_\/___|\\__, |_|  |_|  |_|______|_.__\/ \\__,_|_|   \r\n                        __\/ |                                    \r\n                       |___\/                                    `,
  `  _                         \r\n | |                        \r\n | | ___  _ __ _____      __\r\n | |\/ _ \\| \'__\/ _ \\ \\ \/\\ \/ \/\r\n | | (_) | | | (_) \\ V  V \/ \r\n |_|\\___\/|_|  \\___\/ \\_\/\\_\/  \r\n                            \r\ `,
  `            _       _     \r\n           | |     | |    \r\n   __ _  __| | ___ | |_   \r\n  \/ _\` |\/ _\` |\/ _ \\| __|  \r\n | (_| | (_| | (_) | |_   \r\n  \\__, |\\__,_|\\___\/ \\__|  \r\n     | |                  \r\n     |_|                  \r\n                          `,
];
/* End ASCII Art*/

const terminal = new Terminal({
  theme: {
    background: "#141517",
    cursor: "#ffffff",
    selection: "#ffffff",
  },
  cursorBlink: true,
  cursorStyle: "underline",
  disableStdin: false,
  fontFamily: "monospace",
  fontSize: 14,
  fontWeight: "normal",
  fontWeightBold: "bold",
  renderType: "canvas",
});

terminal.open(document.getElementById("terminal"));

async function connectSerial() {
  try {
    // Prompt user to select any serial port.
    port = await navigator.serial.requestPort();
    await port.open({ baudRate: document.getElementById("baud").value });
    await port.setSignals({ dataTerminalReady: false, requestToSend: false });
    listenToPort();

    textEncoder = new TextEncoderStream();
    writableStreamClosed = textEncoder.readable.pipeTo(port.writable);

    writer = textEncoder.writable.getWriter();
  } catch {
    alert("Serial Connection Failed");
  }
}

async function sendCharacterNumber() {
  document.getElementById("lineToSend").value = String.fromCharCode(
    document.getElementById("lineToSend").value
  );
}

async function sendSerialLine() {
  dataToSend = document.getElementById("lineToSend").value;
  lineHistory.unshift(dataToSend);
  historyIndex = -1; // No history entry selected
  if (document.getElementById("carriageReturn").checked == true)
    dataToSend = dataToSend + "\r";
  if (document.getElementById("addLine").checked == true)
    dataToSend = dataToSend + "\n";
  if (document.getElementById("echoOn").checked == true)
    if (
      dataToSend === "clear" ||
      dataToSend === "clear\r\n" ||
      dataToSend === "clear\r" ||
      dataToSend === "clear\n"
    )
      advancedTerminalClear();
    else appendToAdvancedTerminal(dataToSend);
  if (
    dataToSend === "clear" ||
    dataToSend === "clear\r\n" ||
    dataToSend === "clear\r" ||
    dataToSend === "clear\n"
  )
    advancedTerminalClear();
  if (
    dataToSend === "neofetch" ||
    dataToSend === "neofetch\r\n" ||
    dataToSend === "neofetch\r" ||
    dataToSend === "neofetch\n"
  )
    printToConsole(neofetch_data, "34", false);
  if (
    dataToSend === "contributors" ||
    dataToSend === "contributors\r\n" ||
    dataToSend === "contributors\r" ||
    dataToSend === "contributors\n"
  )
    printContributors();
  //await writer.write(dataToSend);
  document.getElementById("lineToSend").value = "";
  //await writer.releaseLock();
}

function printToConsole(data, color, array) {
  if (array == true) {
    for (var i = 0; i < data.length; i++) {
      terminal.writeln(`\x1B[1;3;${color}m${data[i]}\x1B[0m`);
    }
  } else {
    terminal.writeln(`\x1B[1;3;${color}m${data}\x1B[0m`);
  }
}

function printContributors() {
  printToConsole(
    "The Team:",
    "34",
    false
  );
  printToConsole(contributors[0], "34", false);
  printToConsole(contributors[1], "33", false);
  printToConsole(contributors[2], "32", false);
  printToConsole(contributors[3], "31", false);
  printToConsole(contributors[4], "37", false);
}

async function listenToPort() {
  const textDecoder = new TextDecoderStream();
  const readableStreamClosed = port.readable.pipeTo(textDecoder.writable);
  const reader = textDecoder.readable.getReader();

  // Listen to data coming from the serial device.
  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      // Allow the serial port to be closed later.
      //reader.releaseLock();
      break;
    }
    // value is a string.
    appendToAdvancedTerminal(value);
  }
}

async function appendToAdvancedTerminal(newStuff) {
  terminal.write(
    "\x1B[1;3;32mdev@EyeTrackVR\x1B[0m\x1B[1;3;34m:~$\x1B[0m " + newStuff
  );
}

async function advancedTerminalClear() {
  terminal.clear();
}

function scrollHistory(direction) {
  // Clamp the value between -1 and history length
  historyIndex = Math.max(
    Math.min(historyIndex + direction, lineHistory.length - 1),
    -1
  );
  if (historyIndex >= 0) {
    document.getElementById("lineToSend").value = lineHistory[historyIndex];
  } else {
    document.getElementById("lineToSend").value = "";
  }
}

document
  .getElementById("lineToSend")
  .addEventListener("keyup", async function (event) {
    if (event.keyCode === 13) {
      sendSerialLine();
    } else if (event.keyCode === 38) {
      // Key up
      scrollHistory(1);
    } else if (event.keyCode === 40) {
      // Key down
      scrollHistory(-1);
    }
  });

document.getElementById("baud").value =
  localStorage.baud == undefined ? 9600 : localStorage.baud;
document.getElementById("addLine").checked =
  localStorage.addLine == "false" ? false : true;
document.getElementById("carriageReturn").checked =
  localStorage.carriageReturn == "false" ? false : true;
document.getElementById("echoOn").checked =
  localStorage.echoOn == "false" ? false : true;
