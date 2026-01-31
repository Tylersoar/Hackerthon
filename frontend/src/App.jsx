import { useEffect, useRef, useState } from 'react'
import { Container, Button, Card, Badge, ProgressBar, Alert } from 'react-bootstrap'
import './App.css'
import 'bootstrap/dist/css/bootstrap.min.css'

function App() {
  const [isRecording, setIsRecording] = useState(false);
  const [audioLevel, setAudioLevel] = useState(0);
  const [wsConnected, setWsConnected] = useState(false);
  // const [transcripts, setTranscripts] = useState([]);
  const [transcripts, setTranscripts] = useState([
    {
      id: 1,
      text: "The Earth is flat and has never been proven to be round.",
      timestamp: "10:23:45",
      status: 'complete',
      factCheck: {
        isTrue: false,
        explanation: "The Earth is an oblate spheroid, not flat. This has been proven through satellite imagery, circumnavigation, physics, and observations from space. The spherical nature of Earth has been understood since ancient times."
      }
    },
    {
      id: 2,
      text: "Water boils at 100 degrees Celsius at sea level.",
      timestamp: "10:24:12",
      status: 'complete',
      factCheck: {
        isTrue: true,
        explanation: "This is correct. At standard atmospheric pressure (sea level), pure water boils at exactly 100°C (212°F). This temperature decreases at higher altitudes where atmospheric pressure is lower."
      }
    }
  ]);

  const mediaRecorderReference = useRef(null);
  const audioContextReference = useRef(null);
  const analyserReference = useRef(null);
  const animationFrameReference = useRef(null);
  const wsRef = useRef(null);

  useEffect(() => {
    connectWebSocket();

    // Cleanup when component unmounts
    return () => {
      if (animationFrameReference.current) {
        cancelAnimationFrame(animationFrameReference.current);
      }

      if (wsRef.current) {
        wsRef.current.close();
      }
    }
  }, []);

  const connectWebSocket = () => {
    try {
      const ws = new WebSocket('ws://localhost:8000/ws');

      ws.onopen = () => {
        console.log("WebSocket connected!");
        setWsConnected(true);
      };

      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        console.log("Received from backend: ", data);

        if (data.type === 'transcript') {
          setTranscripts(prev => [...prev, {
            id: data.id || Date.now(),
            text: data.text,
            timestamp: new Date().toLocaleTimeString(),
            status: 'checking',
            factCheck: null
          }]);
        }

        else if (data.type === 'fact_check') {
          setTranscripts(prev => prev.map(t =>
            t.id === data.id
            ? { ...t, status: 'complete', factCheck: data.result }
            : t
          ));
        }
      };

      ws.onerror = (error) => {
        console.error("WebSocket error: ", error);
        setWsConnected(false);
      };

      ws.onclose = () => {
        console.log("WebSocket disconnected.");
        setWsConnected(false);
        setTimeout(connectWebSocket, 3000);
      };

      wsRef.current = ws;
    } catch (error) {
      console.error("Failed to connect to WebSocket: ", error);
    }
  }

  const startRecording = async () => {
    if (!wsConnected) {
      alert("WebSocket not connected! Make sure the backend is running.");
      return;
    }

    try {
      // Request microphone access
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: 16000,
          echoCancellation: true,
          noiseSuppression: true
        }
      });

      // Setup audio visualisation
      audioContextReference.current = new AudioContext();
      analyserReference.current = audioContextReference.current.createAnalyser();
      const source = audioContextReference.current.createMediaStreamSource(stream);
      source.connect(analyserReference.current);
      analyserReference.current.fftSize = 2048;
      analyserReference.current.smoothingTimeConstant = 0.3;
      visualiseAudio();

      // Create MediaRecorder with WebM format
      const mediaRecorder = new MediaRecorder(stream, {
        mimeType: 'audio/webm;codecs=opus',
        audioBitsPerSecond: 16000
      });


      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0 && wsRef.current?.readyState === WebSocket.OPEN) {
          wsRef.current.send(event.data);
          console.log(`Sent audio chunk: ${event.data.size} bytes`);
        }
      };

      mediaRecorder.start(250);
      mediaRecorderReference.current = mediaRecorder;
      setIsRecording(true);

      console.log("Recording started; audio format: ", mediaRecorder.mimeType);
    } catch (error) {
    console.error("Error accessing microphone: ", error);
    alert("Could not access microphone, please check permissions.");
    }
  };

  const stopRecording = () => {
    if (mediaRecorderReference.current && mediaRecorderReference.current.state !== 'inactive') {
      mediaRecorderReference.current.stop();
      mediaRecorderReference.current.stream.getTracks().forEach(track => track.stop());
      setIsRecording(false);
      setAudioLevel(0);

      if (animationFrameReference.current) {
        cancelAnimationFrame(animationFrameReference.current);
      }

      console.log("Recording stopped");
    }
  };

  const visualiseAudio = () => {
    if (!analyserReference.current) return;

    const dataArray = new Uint8Array(analyserReference.current.fftSize);

    const updateLevel = () => {
      analyserReference.current.getByteTimeDomainData(dataArray);

      let sum = 0;
      for(let i = 0; i < dataArray.length; i++) {
        const normalised = (dataArray[i] - 128) / 128;
        sum += normalised * normalised;
      }

      const rms = Math.sqrt(sum / dataArray.length);
      const level = rms * 300;

      setAudioLevel(Math.min(100, level));
      animationFrameReference.current = requestAnimationFrame(updateLevel);
    };

    updateLevel();
  };

  return (
    <Container className='py-5'>
      <h1 className='text-center mb-4'>
        TruthStream
      </h1>

      {!wsConnected && (
        <Alert variant='warning' className='text-center' style={{ maxWidth: '600px', margin: '0 auto 20px' }}>
          Backend not connected!
        </Alert>
      )}

      <Card style={{ maxWidth: '600px', margin: '0 auto' }}>
        <Card.Body>
          <div className='d-flex justify-content-between align-items-center mb-3'>
            <Badge bg={wsConnected ? 'success' : 'danger'}>
              {wsConnected ? 'Connected' : 'Disconnected'}
            </Badge>
            <Badge bg={isRecording ? 'danger' : 'secondary'} className='fs-6'>
              {isRecording ? 'Recording!' : 'Stopped'}
            </Badge>
          </div>

          {isRecording && (
            <div className='mb-4'>
              <small className='text-muted d-block mb-2'>
                Audio Level: {Math.round(audioLevel)}%
              </small>
              <ProgressBar
                now={audioLevel}
                variant={audioLevel > 50 ? "danger" : audioLevel > 20 ? "warning" : "success"}
                style={{ height: '25px' }}
                animated
              />
            </div>
          )}

          <div className='d-grid gap-2'>
            {!isRecording ? (
              <Button
                variant='primary'
                size='lg'
                onClick={startRecording}
                disabled={!wsConnected}>
                  Start Recording
                </Button>
            ) : (
              <Button
                variant='danger'
                size='lg'
                onClick={stopRecording}>
                  Stop Recording
                </Button>
            )}
          </div>

          <div className='mt-3'>
            <small className='text-muted d-block'>
              <strong>Audio Format: </strong> audio/webm (Opus codec, 16kHz, mono)
            </small>
            <small className='text-muted d-block mt-3'>
              Check the browser console to see audio chunks being captured!
            </small>
          </div>
        </Card.Body>
      </Card>

      <Card style={{ maxWidth: '800px', margin: '30px auto' }}>
        <Card.Body>
          <h4 className='mb-3'>
            Live Transcript
          </h4>
          {false ? (
            <p className='text-muted text-center py-4'>
              Start recording to see transcripts appear here!
            </p>
          ) : (
            <div style={{ maxHeight: '400px', overflowY: 'auto' }}>
              {transcripts.map((t) => (
                <div key={t.id} className='mb-3 p-3 border-bottom'>
                      <p className='mb-2' style={{
                        color: t.status === 'complete' && t.factCheck
                        ? (t.factCheck.isTrue ? '#198754' : '#dc3545')
                        : 'inherit',
                        fontWeight: '500',
                        fontSize: '1rem'
                      }}>
                        {t.text}
                      </p>
                    <div className='ms-3'>
                      {t.status === 'checking' && (
                        <span className='text-muted'>
                          Checking...
                        </span>
                      )}
                    </div>
                  {t.factCheck?.explanation && (
                    <small className='text-muted d-block mt-2'>
                      {t.factCheck.explanation}
                    </small>
                  )}
                </div>
              ))}
            </div>
          )}
        </Card.Body>
      </Card>
    </Container>
  )
}

export default App
