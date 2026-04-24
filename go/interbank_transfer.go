
package main

import (
	"bytes"
	"encoding/json"
	"io/ioutil"
	"log"
	"net/http"
	"os"
	"time"
)

type TransferRequest struct {
	FromAccount string  `json:"from_account"`
	ToAccount   string  `json:"to_account"`
	Amount      float64 `json:"amount"`
	BankCode    string  `json:"bank_code"`
	Reference   string  `json:"reference"`
}

type TransferResponse struct {
	Success bool   `json:"success"`
	Message string `json:"message"`
	TxnID   string `json:"txn_id,omitempty"`
}

// AuthResponse matches the expected token response
type AuthResponse struct {
	AccessToken string `json:"accessToken"`
	Data struct {
		AccessToken string `json:"accessToken"`
	} `json:"data"`
}

func getBearerToken(baseURL, username, password, clientId, clientSecret string) (string, error) {
	authURL := baseURL + "/authenticate"
	payload := map[string]string{
		"username":    username,
		"password":    password,
		"clientId":    clientId,
		"clientSecret": clientSecret,
	}
	body, _ := json.Marshal(payload)
	client := &http.Client{Timeout: 15 * time.Second}
	req, err := http.NewRequest("POST", authURL, bytes.NewBuffer(body))
	if err != nil {
		return "", err
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := client.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	respBody, _ := ioutil.ReadAll(resp.Body)
	var authResp AuthResponse
	json.Unmarshal(respBody, &authResp)
	if authResp.AccessToken != "" {
		return authResp.AccessToken, nil
	}
	if authResp.Data.AccessToken != "" {
		return authResp.Data.AccessToken, nil
	}
	return "", nil
}

func processTransfer(req TransferRequest) (TransferResponse, error) {
	baseURL := os.Getenv("NINE_PSB_BASEURL")
	username := os.Getenv("NINE_PSB_USERNAME")
	password := os.Getenv("NINE_PSB_PASSWORD")
	clientId := os.Getenv("CLIENT_ID")
	clientSecret := os.Getenv("CLIENT_SECRET")

	token, err := getBearerToken(baseURL, username, password, clientId, clientSecret)
	if err != nil || token == "" {
		return TransferResponse{Success: false, Message: "Authentication failed"}, err
	}

	resource := "/wallet_other_banks"
	transferURL := baseURL + resource

	payload := map[string]interface{}{
		"customer": map[string]interface{}{
			"account": map[string]interface{}{
				"bank":               req.BankCode,
				"number":             req.ToAccount,
				"senderaccountnumber": req.FromAccount,
				"name":               "Beneficiary Name", // Fill as needed
				"sendername":         "Sender Name",      // Fill as needed
			},
		},
		"order": map[string]interface{}{
			"amount":     req.Amount,
			"currency":   "NGN",
			"description": "Interbank transfer",
			"country":     "NG",
		},
		"narration":      "Interbank transfer",
		"transaction":    map[string]interface{}{ "reference": req.Reference },
		"transactionType": "INTER_BANK",
	}
	body, _ := json.Marshal(payload)
	client := &http.Client{Timeout: 20 * time.Second}
	httpReq, err := http.NewRequest("POST", transferURL, bytes.NewBuffer(body))
	if err != nil {
		return TransferResponse{Success: false, Message: err.Error()}, err
	}
	httpReq.Header.Set("Content-Type", "application/json")
	httpReq.Header.Set("Authorization", "Bearer "+token)

	resp, err := client.Do(httpReq)
	if err != nil {
		return TransferResponse{Success: false, Message: err.Error()}, err
	}
	defer resp.Body.Close()
	respBody, _ := ioutil.ReadAll(resp.Body)
	if resp.StatusCode != 200 {
		return TransferResponse{Success: false, Message: string(respBody)}, nil
	}
	// You may want to parse the response further
	return TransferResponse{Success: true, Message: "Transfer processed", TxnID: req.Reference}, nil
}

func transferHandler(w http.ResponseWriter, r *http.Request) {
	var req TransferRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid request", http.StatusBadRequest)
		return
	}
	resp, err := processTransfer(req)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(resp)
}

func main() {
	http.HandleFunc("/interbank/transfer", transferHandler)
	log.Println("Go Interbank Transfer service running on :8083")
	log.Fatal(http.ListenAndServe(":8083", nil))
}
