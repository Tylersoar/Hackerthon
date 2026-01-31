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
  const [transcriptSegments, setTranscriptSegments] = useState([
    {
      id: 'seg-1',
      text: "Today I want to talk about the economy. The ",
      claimId: null
    },
    {
      id: 'seg-2',
      text: "unemployment rate is at 3%",
      claimId: 'claim-1'
    },
    {
      id: 'seg-3',
      text: " which is historically low. ",
      claimId: null
    },
    {
      id: 'seg-4',
      text: "Water boils at 100 degrees Celsius at sea level",
      claimId: 'claim-2'
    },
    {
      id: 'seg-5',
      text: ". ",
      claimId: null
    },
    {
      id: 'seg-6',
      text: "The Earth is flat",
      claimId: 'claim-3'
    },
    {
      id: 'seg-7',
      text: " and this has been proven by many scientists. Climate change is affecting our planet and ",
      claimId: null
    },
    {
      id: 'seg-8',
      text: "temperatures have risen by 1.5 degrees globally",
      claimId: 'claim-4'
    },
    {
      id: 'seg-9',
      text: " since pre-industrial times. The population of the United States is over 330 million people. Vaccines cause autism according to recent studies. The Great Wall of China is visible from space with the naked eye. Python is the most popular programming language in 2024.",
      claimId: null
    }
  ]);

  const [claims, setClaims] = useState([
    {
      id: 'claim-1',
      text: "unemployment rate is at 3%",
      status: 'complete',
      isTrue: true,
      explanation: "According to the U.S. Bureau of Labor Statistics, the unemployment rate was approximately 3.7% in recent months, which is considered historically low and close to the stated 3%."
    },
    {
      id: 'claim-2',
      text: "Water boils at 100 degrees Celsius at sea level",
      status: 'complete',
      isTrue: true,
      explanation: "This is scientifically accurate. At standard atmospheric pressure (sea level), pure water boils at exactly 100°C (212°F)."
    },
    {
      id: 'claim-3',
      text: "The Earth is flat",
      status: 'complete',
      isTrue: false,
      explanation: "This is false. The Earth is an oblate spheroid. This has been proven through satellite imagery, physics, space exploration, and centuries of scientific observation."
    },
    {
      id: 'claim-4',
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

        // ADD SPLITTING FIX HERE
  //     ws.onmessage = (event) => {
  //       const data = JSON.parse(event.data);
  //       console.log("Received from backend: ", data);

  //       if (data.type === 'transcript') {
  //         setTranscriptSegments(prev => [...prev, {
  //              id: `seg-${Date.now()}`,
  //              text: data.text,
  //              claimId: null
  //        }]);
  //       } else if (data.type === 'claim_detected') {
            //  const claimId = data.id;

            //  setTranscriptSegments(prev => [...prev, {
            //   id: `seg-${Date.now()}`,
            //   text: data.claim,
            //   claimId: claimId
            //  }]);

  //         setClaims(prev => [...prev, {
  //           id: claimId,
  //           text: data.claim,
  //           status: 'checking',
  //           isTrue: null,
  //           explanation: null
  //         }]);
  //       }

  //       else if (data.type === 'fact_check') {
  //         setClaims(prev => prev.map(c =>
  //           c.id === data.id
  //           ? { ...c,
  //               status: 'complete',
  //               isTrue: data.result.isTrue,
  //                explanation: data.result.explanation
  //                }
  //           : c
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

  const renderTranscript = () => {
    return transcriptSegments.map((segment) => {
      if (!segment.claimId) {
        return <span key={segment.id}>{segment.text}</span>;
      }

      const claim = claims.find(c => c.id === segment.claimId);
      let colour = '#000000';

      if (claim) {
        if (claim.status === 'checking') {
          colour = '#6c757d';
        } else if (claim.status === 'complete') {
          colour = claim.isTrue ? '#10b981' : '#dc3545';
        }
      }

      return (
        <span
          key={segment.id}
          style={{
            color: colour,
            fontWeight: '500',
            cursor: claim?.status === 'complete' ? 'pointer' : 'default'
          }}
          onClick={() => claim?.status === 'complete' && handleClaimClick(claim)}>
            {segment.text}
        </span>
      );
    });
  };

  const handleClaimClick = (claim) => {
    if (claim.status === 'complete') {
      setSelectedClaim(claim);
      setShowModal(true);
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
    <Container fluid style={{ height: '100vh', padding: '20px' }}>
      <Row style={{ height: '100%' }}>
        {/* Left-side - main content */}
        <Col md={8} style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
          <h1 className='mb-4'>
            TruthStream
          </h1>

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
          <Card style={{ flex: 1, overflow: 'hidden', border: 'none', backgroundColor: 'rgba(0, 0, 0, 256)' }}>
            <Card.Body style={{ height: '100%', overflow: 'auto' }}>
              <h2 className='mb-3'>
                Live Transcript
              </h2>
              <div style={{ fontSize: '1.1rem', lineHeight: 1.8 }}>
                <p>{renderTranscript()}</p>
              </div>
            </Card.Body>
          </Card>
        </Col>

        {/* Right side - Claims sidebar */}
        <Col md={4} style={{
          height: '100%',
          paddingLeft: '20px'
        }}>
          <Card style={{ height: '100%', border: 'none', backgroundColor: 'rgba(0, 0, 0, 256)' }}>
            <Card.Body style={{ height: '100%', overflow: 'auto' }}>
              <h3 className='mb-4'>
                Claims
              </h3>

              {claims.length === 0 ? (
                <p className='text-muted'>
                  No claims detected yet
                </p>
              ) : (
                <div>
                  {claims.map((claim) => (
                    <div
                      className='bounce-in'
                      key={claim.id}
                      onClick={() => handleClaimClick(claim)}
                      style={{
                        padding: '15px',
                        marginBottom: '15px',
                        borderRadius: '8px',
                        backgroundColor: 'rgba(0, 0, 0, 256)',
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
                          : (claim.isTrue ? '#10b981' : '#dc3545'),
                          fontWeight: '500',
                          fontSize: '0.95rem'
                        }}>
                          {claim.text}
                        </p>
                        {claim.status === 'checking' && (
                          <small className='d-block mt-2'>
                            ⏳ Checking...
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
        <Modal.Header closeButton>
          <Modal.Title>
            Claim Details
          </Modal.Title>
        </Modal.Header>
        <Modal.Body>
          {selectedClaim && (
            <>
              <p style={{
                color: selectedClaim.isTrue ? '#10b981' : '#dc3545',
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
      </Modal>
    </Container>
  )
}

export default App
