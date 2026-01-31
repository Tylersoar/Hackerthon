import { useEffect, useRef, useState } from 'react'
import { Container, Button, Card, Badge, ProgressBar } from 'react-bootstrap'
import './App.css'
import 'bootstrap/dist/css/bootstrap.min.css'

function App() {
  const [isRecording, setIsRecording] = useState(false);
  const [audioLevel, setAudioLevel] = useState(0);
  const [audioChunks, setAudioChunks] = useState([]);

  const mediaRecorderReference = useRef(null);
  const audioContextReference = useRef(null);
  const analyserReference = useRef(null);
  const animationFrameReference = useRef(null);
  const chunksReference = useRef([]);

  useEffect(() => {
    // Cleanup when component unmounts
    return () => {
      if (animationFrameReference.current) {
        cancelAnimationFrame(animationFrameReference.current);
      }
    }
  }, []);

  const startRecording = async () => {
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

      chunksReference.current = [];

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          chunksReference.current.push(event.data);
          // Log audio chunk information
          console.log(`Audio chunk: ${event.data.size} bytes, type: ${event.data.type}`);
          // TODO: send to backend here
        }
      };

      mediaRecorder.onstop = () => {
        setAudioChunks(chunksReference.current);
      }

      mediaRecorder.start(250);
      mediaRecorderReference.current = mediaRecorder;
      setIsRecording(true);
      setAudioChunks([]);

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

  const downloadRecording = () => {
    if (audioChunks.length === 0) {
      alert("No recording available to download!");
      return;
    } 

    const blob = new Blob(audioChunks,  { type: 'audio/webm' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `recording-${Date.now()}.webm`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    console.log("Recording downloaded!");
  }

  return (
    <Container className='py-5'>
      <h1 className='text-center mb-4'>
        TruthStream
      </h1>

      <Card style={{ maxWidth: '600px', margin: '0 auto' }}>
        <Card.Body>
          <div className='d-flex justify-content-center mb-3'>
            <Badge bg={isRecording ? 'danger' : 'secondary'} className='fs-6'>
              {isRecording ? 'Recording!' : 'Stopped'}
            </Badge>
          </div>

          {isRecording && (
            <div className='mb-4'>
              <small className='text-muted d-block mb-2'>
                Audio Level:
              </small>
              <ProgressBar
                now={audioLevel}
                variant="success"
                style={{ height: '25px' }}
              />
            </div>
          )}

          <div className='d-grid gap-2'>
            {!isRecording ? (
              <Button
                variant='primary'
                size='lg'
                onClick={startRecording}>
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

            {audioChunks.length > 0 && !isRecording && (
              <Button
                variant='success'
                size='lg'
                onClick={downloadRecording}>
                  Download Recording
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
    </Container>
  )
}

export default App
