import { Client, ResultCallback } from "minio";
import fetch from "node-fetch";
import { Stream } from "stream";

/**
 * Expected environment variables to configure minio client.
 */
export interface IMinioEnv extends NodeJS.ProcessEnv {
  MINIO_END_POINT?: string;
  MINIO_PORT?: string;
  MINIO_ACCESS_KEY?: string;
  MINIO_SECRET_KEY?: string;
  MINIO_SECURE?: string;
  MINIO_REGION?: string;
}

type MetaDataResult = {
  AccessKeyId: string;
  SecretAccessKey: string;
  Expiration: string;
  Token: string;
};

export class MinioClientWrapper {
  /**
   * AWS EC2 metadata store.
   */
  public readonly metadataUrl: string =
    "http://169.254.169.254/latest/meta-data";
  /**
   * Promise to EC2 instance profile if available.
   */
  public readonly iamRole!: Promise<string | void>;

  /**
   * promise to minio client
   */
  private _client?: Promise<Client | void>;

  /**
   * expiration time (epoch time in ms) for IAM role credentials.
   * If access credentials are provided, expiration time will be
   * -1.
   */
  protected expiration: number = 0;

  /**
   * Class that returns a minio client based on environment
   * variables. Fallback to EC2 IAM role credentials if
   * access key and secret are empty strings.
   */
  constructor() {
    // get the iam role for current ec2 instance
    this.iamRole = fetch(`${this.metadataUrl}/iam/security-credentials/`)
      .then(resp => resp.ok && resp.text())
      .catch(error => console.error(error));
    // initialize client
    this.init();
  }

  /**
   * @returns Promise to a minio client.
   */
  client() {
    // create new minio client if required
    this._client = this.createClient();
    return this._client;
  }

  /**
   * Initialize a minio client from the environment variables.
   * @param env Process environment variables
   */
  protected init(env: IMinioEnv = process.env) {
    const {
      MINIO_END_POINT: endPoint = "minio-service.kubeflow",
      MINIO_PORT: port = "9000",
      MINIO_ACCESS_KEY: accessKey = "minio",
      MINIO_SECRET_KEY: secretKey = "minio123",
      MINIO_SECURE: secure = "false",
      MINIO_REGION: region
    } = env;

    // for s3 bucket with provisioned access key and access secret
    if (endPoint.toLowerCase() === "s3.amazonaws.com") {
      // no credential provided
      if (accessKey.length === 0 || secretKey.length === 0) return;
      // never expire
      this.expiration = -1;

      // create persistent client
      this._client = Promise.resolve(
        new Client({ accessKey, secretKey, region, endPoint })
      );
      return;
    }
    // normal minio conf
    const asBool = (value?: string) =>
      !!value ? ["true", "1"].indexOf(value.toLowerCase()) >= 0 : false;

    // never expire
    this.expiration = -1;

    // create persistent client
    this._client = Promise.resolve(
      new Client({
        accessKey,
        secretKey,
        endPoint,
        port: parseInt(port, 10),
        useSSL: asBool(secure)
      } as any) // minio Client type definition is out-dated
    );
  }

  protected getClientFromEc2MetaData(iamRole?: string) {
    if (!iamRole) throw new Error("Unable to find IAM role for EC2 instance.");
    const toClient = ({
      AccessKeyId: accessKey,
      SecretAccessKey: secretKey,
      Expiration,
      Token: sessionToken
    }: MetaDataResult) => {
      this.expiration = new Date(Expiration).getTime();
      return new Client({
        endPoint: "s3.amazonaws.com",
        accessKey,
        secretKey,
        sessionToken
      });
    };
    return fetch(`${this.metadataUrl}/iam/security-credentials/${iamRole}`)
      .then(resp => resp.json())
      .then(toClient);
  }

  /**
   * Retrieve ec2 iam role credentials and create a new minio Client
   */
  protected createClient() {
    // return persistent client
    if (this.expiration < 0) return this._client;

    // return client if it exists and credentials are not expired.
    if (!!this._client && this.expiration > Date.now()) {
      return this._client;
    }
    // create new client with IAM credentials
    this._client = this.iamRole.then(
      iamRole => iamRole && this.getClientFromEc2MetaData(iamRole)
    );
    return this._client;
  }

  /**
   * Proxy for minio getObject function.
   * @param bucket Bucket name
   * @param key Object to retrieve
   * @param cb Callback function
   */
  getObject(bucket: string, key: string, cb: ResultCallback<Stream>) {
    return this.client().then(
      client => client && client.getObject(bucket, key, cb)
    );
  }
}
