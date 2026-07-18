import serial
import time
import threading


class GSMSender:
    def __init__(self, port, baudrate=115200, timeout=5):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.ser = None
        self.lock = threading.Lock()

    def connect(self):
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
            time.sleep(2)
            self.ser.reset_input_buffer()
            self._send_at("ATZ")
            self._send_at("AT+CMGF=1")
            return True
        except serial.SerialException as e:
            print(f"Failed to connect to GSM modem on {self.port}: {e}")
            self.ser = None
            return False

    def disconnect(self):
        if self.ser:
            try:
                self.ser.close()
            except Exception:
                pass
            self.ser = None

    def _send_at(self, command, wait=1):
        if not self.ser:
            return None
        try:
            self.ser.write((command + "\r").encode())
            time.sleep(wait)
            response = self.ser.read(self.ser.in_waiting).decode(errors='ignore')
            return response
        except Exception:
            return None

    def send_sms(self, phone_number, message, sender_id=None):
        with self.lock:
            if not self.ser:
                if not self.connect():
                    return "ERROR: Modem not connected"
            try:
                self.ser.write(b'AT+CMGF=1\r')
                time.sleep(0.5)
                self.ser.read(self.ser.in_waiting)

                if sender_id:
                    self.ser.write(f'AT+CSCA="{sender_id}"\r'.encode())
                    time.sleep(0.5)
                    self.ser.read(self.ser.in_waiting)

                self.ser.write(f'AT+CMGS="{phone_number}"\r'.encode())
                time.sleep(0.5)
                self.ser.read(self.ser.in_waiting)

                self.ser.write(message.encode() + b"\x1A")
                time.sleep(3)
                resp = self.ser.read(self.ser.in_waiting).decode(errors='ignore')

                if '+CMGS:' in resp:
                    return resp
                elif 'ERROR' in resp:
                    return f"ERROR: {resp}"
                else:
                    return resp
            except serial.SerialException as e:
                self.ser = None
                return f"ERROR: {e}"
            except Exception as e:
                return f"ERROR: {e}"

    def send_bulk_sms(self, numbers, message, progress_cb=None, sender_ids=None):
        results = {}
        for idx, number in enumerate(numbers):
            sender_id = None
            if sender_ids and idx < len(sender_ids):
                sender_id = sender_ids[idx]
            resp = self.send_sms(number, message, sender_id=sender_id)
            results[number] = resp
            if progress_cb:
                progress_cb(idx + 1, len(numbers), f"Sent to {number}")
            time.sleep(1)
        return results
