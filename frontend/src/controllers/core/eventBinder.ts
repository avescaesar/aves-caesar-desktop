export type EventBinder = (element: EventTarget | null, eventName: string, listener: EventListener, options?: AddEventListenerOptions) => void;
