export interface SessionInfo {
  idcode: string;
  peerIp: string;
  state: "connected" | "cfg1_received" | "cfg2_sent" | "streaming" | "disconnected";
}

export interface ConfigInfo {
  cfgType: number;
  version: number;
  stn: string;
  idcode: string;
  formatFlags: number;
  period: number;
  measRate: number;
  phnmr: number;
  annmr: number;
  dgnmr: number;
  channelNames: string[];
  anunit: number[];
}

export interface DataInfo {
  soc: number;
  fracsec: number;
  stat: number;
  analog: number[];
  digital: number[];
  phasors: [number, number][];
}

export interface RawFrameInfo {
  idcode: string;
  direction: "send" | "recv";
  hex: string;
}

export type PmuEvent =
  | { type: "SessionCreated"; idcode: string; peer_ip: string }
  | { type: "SessionDisconnected"; idcode: string }
  | { type: "Cfg1Received"; idcode: string; cfg: ConfigInfo }
  | { type: "Cfg2Sent"; idcode: string }
  | { type: "Cfg2Received"; idcode: string; cfg: ConfigInfo }
  | { type: "StreamingStarted"; idcode: string }
  | { type: "StreamingStopped"; idcode: string }
  | { type: "DataFrame"; idcode: string; data: DataInfo }
  | { type: "RawFrame"; idcode: string; direction: string; hex: string }
  | { type: "HeartbeatTimeout"; idcode: string }
  | { type: "Error"; idcode: string; error: string };
