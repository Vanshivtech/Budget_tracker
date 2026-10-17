import { registerPlugin, PluginListenerHandle } from '@capacitor/core';

export interface SmsMessageData {
  sender: string;
  body: string;
  timestamp: number;
}

export interface BackfillResult {
  status: string;
  count: number;
  sms: SmsMessageData[];
}

export interface SmsReaderPluginInterface {
  startListening(): Promise<{ status: string }>;
  stopListening(): Promise<{ status: string }>;
  backfillSms(options?: { days?: number }): Promise<BackfillResult>;
  addListener(
    eventName: 'smsReceived',
    listenerFunc: (message: SmsMessageData) => void,
  ): Promise<PluginListenerHandle> & PluginListenerHandle;
  removeAllListeners(): Promise<void>;
}

const SmsReaderPlugin = registerPlugin<SmsReaderPluginInterface>('SmsReaderPlugin');

export default SmsReaderPlugin;

export const startListening = () => SmsReaderPlugin.startListening();
export const stopListening = () => SmsReaderPlugin.stopListening();
export const backfillSms = (days = 90) => SmsReaderPlugin.backfillSms({ days });
export const addListener = (
  eventName: 'smsReceived',
  callback: (message: SmsMessageData) => void,
) => SmsReaderPlugin.addListener(eventName, callback);
