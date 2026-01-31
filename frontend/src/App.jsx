import { useEffect, useRef, useState } from 'react'
import { Container, Button, Card, Row, Modal, Col } from 'react-bootstrap'
import './App.css'
import 'bootstrap/dist/css/bootstrap.min.css'

function App() {
  const [isRecording, setIsRecording] = useState(false);
  const [audioLevel, setAudioLevel] = useState(0);
  const [wsConnected, setWsConnected] = useState(true);

const [showModal, setShowModal] = useState(false);
const [selectedClaim, setSelectedClaim] = useState(null);

  // const [transcripts, setTranscripts] = useState([]);
  const [transcript, setTranscript] = useState(
    "Today I want to talk about the economy. The unemployment rate is at 3% which is historically low. " +
    "Water boils at 100 degrees Celsius at sea level. The Earth is flat and this has been proven by many scientists. " +
    "Climate change is affecting our planet and temperatures have risen by 1.5 degrees globally since pre-industrial times. " +
    "The population of the United States is over 330 million people. Vaccines cause autism according to recent studies. " +
    "The Great Wall of China is visible from space with the naked eye. Python is the most popular programming language in 2024."
  );

  const [claims, setClaims] = useState([
    {
      id: 1,
      text: "unemployment rate is at 3%",
      status: 'complete', // 'checking' or 'complete'
      isTrue: true,
      explanation: "According to the U.S. Bureau of Labor Statistics, the unemployment rate was approximately 3.7% in recent months, which is considered historically low and close to the stated 3%."
    },
    {
      id: 2,
      text: "Water boils at 100 degrees Celsius at sea level",
      status: 'complete',
      isTrue: true,
      explanation: "This is scientifically accurate. At standard atmospheric pressure (sea level), pure water boils at exactly 100°C (212°F)."
    },
    {
      id: 3,
      text: "The Earth is flat",
      status: 'complete',
      isTrue: false,
      explanation: "This is false. The Earth is an oblate spheroid. This has been proven through satellite imagery, physics, space exploration, and centuries of scientific observation."
    },
    {
      id: 4,
      text: "temperatures have risen by 1.5 degrees globally",
      status: 'checking',
      isTrue: null,
      explanation: null
    }
  ]);

  const mediaRecorderReference = useRef(null);
  const audioContextReference = useRef(null);
  const analyserReference = useRef(null);
  const animationFrameReference = useRef(null);
  const wsRef = useRef(null);

  useEffect(() => {
    // connectWebSocket();

    // Cleanup when component unmounts
    return () => {
      if (animationFrameReference.current) {
        cancelAnimationFrame(animationFrameReference.current);
      }

      // if (wsRef.current) {
      //   wsRef.current.close();
      // }
    }
  }, []);

  // const connectWebSocket = () => {
  //   try {
  //     const ws = new WebSocket('ws://localhost:8000/ws');

  //     ws.onopen = () => {
  //       console.log("WebSocket connected!");
  //       setWsConnected(true);
  //     };

  //     ws.onmessage = (event) => {
  //       const data = JSON.parse(event.data);
  //       console.log("Received from backend: ", data);

  //       if (data.type === 'transcript') {
  //         setTranscript(prev => prev + " " + data.text);
  //       } else if (data.type === 'claim_detected') {
  //         setClaims(prev => [...prev, {
  //           id: data.id,
  //           text: data.claim,
  //           status: 'checking',
  //           isTrue: null,
  //           explanation: null
  //         }]);
  //       }

  //       else if (data.type === 'fact_check') {
  //         setTranscripts(prev => prev.map(t =>
  //           t.id === data.id
  //           ? { ...t, status: 'complete', factCheck: data.result }
  //           : t
  //         ));
  //       }
  //     };

  //     ws.onerror = (error) => {
  //       console.error("WebSocket error: ", error);
  //       setWsConnected(false);
  //     };

  //     ws.onclose = () => {
  //       console.log("WebSocket disconnected.");
  //       setWsConnected(false);
  //       setTimeout(connectWebSocket, 3000);
  //     };

  //     wsRef.current = ws;
  //   } catch (error) {
  //     console.error("Failed to connect to WebSocket: ", error);
  //   }
  // }

  const startRecording = async () => {
    // if (!wsConnected) {
    //   alert("WebSocket not connected! Make sure the backend is running.");
    //   return;
    // }

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
        // if (event.data.size > 0 && wsRef.current?.readyState === WebSocket.OPEN) {
        //   wsRef.current.send(event.data);
        //   console.log(`Sent audio chunk: ${event.data.size} bytes`);
        // }
        if (event.data.size > 0) {
          console.log(`Captured audio chunk: ${event.data.size} bytes`);
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

  const highlightTranscript = () => {
    let highlightedText = transcript;

    claims.forEach(claim => {
      const regex = new RegExp(`(${claim.text})`, 'gi');
      let colour = '#6c757d';

      if (claim.status === 'complete') {
        colour = claim.isTrue ? '#198754' : '#dc3545';
      }

      highlightedText = highlightedText.replace(
        regex,
        `<span style="color: ${colour}; font-weight: 500;>$1</span>`
      )
    });

    return { __html: highlightedText };
  }

  const handleClaimClick = (claim) => {
    if (claim.status === 'complete') {
      setSelectedClaim(claim);
      setShowModal(true);
    }
  }

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
    <Container fluid style={{ height: '100vh', padding: '20px' }}>
      <Row style={{ height: '100%' }}>
        {/* Left-side - main content */}
        <Col md={8} style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
          <h2 className='mb-4'>
            TruthStream
          </h2>

          <div className='mb-4'>
            <Button
              variant={isRecording ? 'danger' : 'primary'}
              size='lg'
              onClick={isRecording ? stopRecording : startRecording}
              // disabled={!wsConnected}
              style={{ minWidth: '200px' }}>
                {isRecording ? 'Stop Recording' : 'Start Recording'}
            </Button>
            {/* {!wsConnected && (
              <small className='text-danger d-block mt-2'>
                Backend not connected!
              </small>
            )} */}
          </div>

          {/* Live transcript */}
          <Card style={{ flex: 1, overflow: 'hidden' }}>
            <Card.Body style={{ height: '100%', overflow: 'auto' }}>
              <h5 className='mb-3'>
                Live Transcript
              </h5>
              <div style={{ fontSize: '1.1rem', lineHeight: 1.8 }}>
                <p dangerouslySetInnerHTML={highlightTranscript()} />
              </div>
            </Card.Body>
          </Card>
        </Col>

        {/* Right side - Claims sidebar */}
        <Col md={4} style={{
          height: '100%',
          borderLeft: '2px solid #dee2e6',
          paddingLeft: '20px'
        }}>
          <Card style={{ height: '100%', border: 'none' }}>
            <Card.Body style={{ height: '100%', overflow: 'auto' }}>
              <h5 className='mb-4'>
                Claims
              </h5>

              {claims.length === 0 ? (
                <p className='text-muted'>
                  No claims detected yet
                </p>
              ) : (
                <div>
                  {claims.map((claim) => (
                    <div
                      key={claim.id}
                      onClick={() => handleClaimClick(claim)}
                      style={{
                        padding: '15px',
                        marginBottom: '15px',
                        borderRadius: '8px',
                        backgroundColor: '#f8f9fa',
                        border: '1px solid #dee2e6',
                        cursor: claim.status === 'complete' ? 'pointer' : 'default',
                        transition: 'all 0.2s'
                      }}
                      onMouseEnter={(e) => {
                        if (claim.status === 'complete') {
                          e.currentTarget.style.transform = 'translateY(-2px)';
                          e.currentTarget.style.boxShadow = '0 4px 8px rgba(0, 0, 0, 0.1)'
                        }
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.transform = 'translateY(0)';
                        e.currentTarget.style.boxShadow = 'none';
                      }}>
                        <p style={{
                          margin: 0,
                          color: claim.status === 'checking'
                          ? '#6c757d'
                          : (claim.isTrue ? '#198754' : '#dc3545'),
                          fontWeight: '500',
                          fontSize: '0.95rem'
                        }}>
                          {claim.text}
                        </p>
                        {claim.status === 'checking' && (
                          <small className='text-muted d-block mt-2'>
                            Checking...
                          </small>
                        )}
                        {claim.status === 'complete' && (
                          <small style={{
                            color: claim.isTrue ? '#198754' : '#dc3545',
                            display: 'block',
                            marginTop: '8px',
                            fontWeight: '600'
                          }}>
                          </small>
                        )}
                    </div>
                  ))}
                </div>
              )}
            </Card.Body>
          </Card>
        </Col>
      </Row>

      {/* Modal for claim explanation */}
      <Modal show={showModal} onHide={() => setShowModal(false)} centered>
        <Modal.Header>
          <Modal.Title>
            Claim Details
          </Modal.Title>
        </Modal.Header>
        <Modal.Body>
          {selectedClaim && (
            <>
              <p style={{
                color: selectedClaim.isTrue ? '#198754' : '#dc3545',
                fontWeight: '600',
                fontSize: '1.1rem',
                marginBottom: '15px'
              }}>
                {selectedClaim.text}
              </p>
              <p style={{
                fontStyle: 'italic',
                color: '#6c757d',
                lineHeight: '1.6'
              }}>
                {selectedClaim.explanation}
              </p>
            </>
          )}
        </Modal.Body>
        <Modal.Footer>
          <Button variant='secondary' onClick={() => setShowModal(false)}>
            Close
          </Button>
        </Modal.Footer>
      </Modal>
    </Container>
  )
}

export default App
