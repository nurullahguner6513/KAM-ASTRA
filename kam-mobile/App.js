import React, { useState, useEffect, useRef } from 'react';
import { StyleSheet, Text, View, TextInput, TouchableOpacity, ScrollView, Platform, Linking } from 'react-native';
import * as Speech from 'expo-speech';

export default function App() {
  const [ip, setIp] = useState('192.168.1.147');
  const [connected, setConnected] = useState(false);
  const [status, setStatus] = useState('Bekleniyor...');
  const [logs, setLogs] = useState([]);
  const [message, setMessage] = useState('');
  
  const ws = useRef(null);

  const addLog = (msg) => {
    setLogs(prev => [...prev, msg].slice(-10));
  };

  const connectServer = () => {
    if (ws.current) {
      ws.current.close();
    }
    setStatus('Bağlanıyor...');
    const url = `ws://${ip}:8765`;
    ws.current = new WebSocket(url);

    ws.current.onopen = () => {
      setConnected(true);
      setStatus('KAM\'a Bağlandı');
      addLog('Bağlantı başarılı.');
    };

    ws.current.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        if (data.type === 'speak') {
          addLog(`KAM: ${data.text}`);
          Speech.speak(data.text, { language: 'tr-TR' });
        } else if (data.type === 'command') {
          addLog(`KOMUT: ${data.action}`);
          executeCommand(data.action, data.payload);
        }
      } catch (err) {
        addLog(`Bilinmeyen Mesaj: ${e.data}`);
      }
    };

    ws.current.onerror = (e) => {
      setStatus('Bağlantı Hatası!');
      addLog(`Hata oluştu.`);
    };

    ws.current.onclose = () => {
      setConnected(false);
      setStatus('Bağlantı Koptu');
      addLog('Bağlantı koptu.');
    };
  };

  const executeCommand = async (action, payload) => {
    try {
      if (action === 'open_app') {
        const urls = {
          'youtube': 'vnd.youtube://',
          'spotify': 'spotify://',
          'whatsapp': 'whatsapp://'
        };
        const url = urls[payload] || payload;
        await Linking.openURL(url);
      } else if (action === 'call') {
        await Linking.openURL(`tel:${payload}`);
      }
    } catch (e) {
      addLog(`Komut Başarısız: ${e.message}`);
    }
  };

  const sendMessage = () => {
    if (message.trim() === '') return;
    if (ws.current && ws.current.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify({ type: 'text', content: message }));
      addLog(`Sen: ${message}`);
      setMessage('');
    } else {
      addLog('Sunucuya bağlı değil.');
    }
  };

  return (
    <View style={styles.container}>
      <Text style={styles.title}>K.A.M Mobile</Text>
      
      <View style={styles.connectionBox}>
        <TextInput 
          style={styles.input} 
          value={ip} 
          onChangeText={setIp} 
          placeholder="PC IP Adresi"
          placeholderTextColor="#666"
        />
        <TouchableOpacity style={styles.btn} onPress={connectServer}>
          <Text style={styles.btnText}>{connected ? 'Yeniden Bağlan' : 'Bağlan'}</Text>
        </TouchableOpacity>
      </View>

      <Text style={[styles.status, { color: connected ? '#00ffcc' : '#ff4444' }]}>
        {status}
      </Text>

      <View style={styles.messageBox}>
        <TextInput 
          style={styles.messageInput} 
          value={message} 
          onChangeText={setMessage} 
          placeholder="Mesaj yaz..."
          placeholderTextColor="#666"
        />
        <TouchableOpacity style={styles.sendBtn} onPress={sendMessage} disabled={!connected}>
          <Text style={styles.btnText}>Gönder</Text>
        </TouchableOpacity>
      </View>

      <ScrollView style={styles.logs}>
        {logs.map((l, i) => <Text key={i} style={styles.logText}>{l}</Text>)}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0a0a0c',
    padding: 20,
    paddingTop: 60,
  },
  title: {
    fontSize: 28,
    fontWeight: 'bold',
    color: '#00ffcc',
    textAlign: 'center',
    marginBottom: 20,
  },
  connectionBox: {
    flexDirection: 'row',
    marginBottom: 20,
  },
  input: {
    flex: 1,
    backgroundColor: '#1a1a1c',
    color: '#fff',
    padding: 10,
    borderRadius: 5,
    borderWidth: 1,
    borderColor: '#333',
    marginRight: 10,
  },
  btn: {
    backgroundColor: '#00ffcc',
    padding: 15,
    borderRadius: 5,
    justifyContent: 'center',
  },
  btnText: {
    color: '#000',
    fontWeight: 'bold',
  },
  status: {
    textAlign: 'center',
    fontSize: 18,
    marginBottom: 20,
  },
  messageBox: {
    flexDirection: 'row',
    marginBottom: 20,
  },
  messageInput: {
    flex: 1,
    backgroundColor: '#1a1a1c',
    color: '#fff',
    padding: 15,
    borderRadius: 5,
    borderWidth: 1,
    borderColor: '#00ffcc',
    marginRight: 10,
  },
  sendBtn: {
    backgroundColor: '#00ffcc',
    padding: 15,
    borderRadius: 5,
    justifyContent: 'center',
  },
  logs: {
    flex: 1,
    backgroundColor: '#111',
    padding: 10,
    borderRadius: 5,
  },
  logText: {
    color: '#00ffcc',
    marginBottom: 5,
    fontFamily: Platform.OS === 'ios' ? 'Courier' : 'monospace',
  }
});
